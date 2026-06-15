#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from core.chapter_utils import chapter_float_key
from core.disk_cache import search_cache
from core.html_utils import normalize_image_url, url_ext
from core.http_pool import HTTP_TIMEOUT, HttpPool
from core.models import Chapter, SearchResult, SeriesDetails, chapter_to_filename
from core.throttle import rate_limiter

from . import BaseSource

logger = logging.getLogger(__name__)

_MAX_PAGES    = 500
_CATALOG_TTL  = 60 * 60 * 24 * 3   # 3 días  — el catálogo cambia poco
_PAGE_TTL     = 60 * 60 * 24 * 7   # 7 días  — páginas individuales, más estables
_PAGE_WORKERS = 4                   # hilos paralelos para descargar páginas del catálogo


class IkigaiSource(BaseSource):
    type = 'manga'
    label = 'Ikigai'
    BASE_URL      = "https://visorikigai.yomod.xyz"
    CATALOGO_BASE = "https://visorikigai.yomod.xyz/series/"
    UA            = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    # Lock y timestamp a nivel de clase: compartidos entre todas las instancias/workers
    _refresh_lock     = threading.Lock()
    _last_refresh_ts  = 0.0
    _REFRESH_COOLDOWN = 60 * 60 * 24   # 24 horas entre refrescos en background

    def __init__(self):
        self.scraper = HttpPool.get_scraper()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, **kwargs):
        rate_limiter.wait(url)
        kwargs.setdefault('timeout', HTTP_TIMEOUT)
        extra_headers = kwargs.pop('headers', {})
        headers = {**self._headers, **extra_headers}
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _fetch_url(self, url: str, **kwargs) -> str:
        return self._get(url, **kwargs).text

    def _get_with_retry(self, url: str, retries: int = 3,
                        backoff: float = 1.0, **kwargs):
        last_exc = None
        for attempt in range(retries):
            try:
                return self._get(url, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    wait = backoff * (2 ** attempt)
                    logger.warning(f"Ikigai: reintento {attempt + 1}/{retries - 1} "
                                   f"para {url} (espera {wait:.1f}s): {exc}")
                    time.sleep(wait)
        raise last_exc

    # -----------------------------------------------------------------------
    # URL helpers
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Catálogo
    # -----------------------------------------------------------------------

    @staticmethod
    def _has_next_page(soup: BeautifulSoup, next_page: int) -> bool:
        """Detecta si existe un enlace a la página siguiente."""
        param = f"pagina={next_page}"
        for a in soup.find_all('a', href=True):
            if param in a['href']:
                return True
        return False

    @staticmethod
    def _parse_page_links(soup: BeautifulSoup) -> list[dict]:
        """Extrae series de una página del catálogo, ignorando enlaces de paginación."""
        items: list[dict] = []
        for a in soup.select('a[href^="/series/"]'):
            href = a.get('href', '')
            if re.search(r'[?&]pagina=', href):
                continue
            slug = href.rstrip('/').split('/')[-1]
            if not slug:
                continue

            title = ''
            h3 = a.find('h3')
            if h3:
                title = h3.get_text(strip=True)
            if not title:
                img_tag = a.find('img')
                if img_tag and img_tag.get('alt'):
                    title = img_tag['alt'].strip()
            if not title:
                title = a.get('title', '').strip()
            if not title:
                title = slug.replace('-', ' ').title()

            cover = ''
            img_tag = a.find('img')
            if img_tag:
                cover = img_tag.get('src', '')

            items.append({'id': slug, 'title': title, 'cover': cover})
        return items

    def _fetch_page(self, page: int) -> tuple[int, list[dict], bool]:
        """
        Descarga UNA página del catálogo. Devuelve (page, items, has_next).
        Intenta caché primero; si no hay, hace la petición HTTP.
        Diseñada para llamarse desde un ThreadPoolExecutor.
        """
        page_key   = f"ikigai:catalog_page:{page}"
        page_items = search_cache.get(page_key)

        if page_items is not None:
            # En caché — no sabemos has_next sin parsear HTML, así que asumimos True
            # (el llamador detiene cuando ya no llegan items nuevos)
            return page, page_items, True

        url = (self.CATALOGO_BASE if page == 1
               else f"{self.CATALOGO_BASE}?pagina={page}")
        try:
            html = self._fetch_url(url)
        except Exception as exc:
            logger.exception(f"Ikigai: error al cargar catálogo página {page}: {exc}")
            return page, [], False

        soup       = BeautifulSoup(html, 'html.parser')
        page_items = self._parse_page_links(soup)
        has_next   = self._has_next_page(soup, page + 1)

        if page_items:
            search_cache.set(page_key, page_items, ttl=_PAGE_TTL)

        return page, page_items, has_next

    def _fetch_full_catalog(self) -> list[dict]:
        """
        Descarga el catálogo completo en paralelo.

        Estrategia:
          1. Descarga las primeras _PAGE_WORKERS páginas en paralelo.
          2. Si alguna devuelve has_next=False o 0 items, detiene la exploración.
          3. Continúa en lotes de _PAGE_WORKERS hasta agotar el catálogo.

        Ventaja: en un catálogo de 50 páginas con 8 workers, el tiempo pasa
        de ~50 × 3s = 150s  →  ~7 lotes × 3s = ~21s.
        """
        results:    list[dict] = []
        seen_slugs: set[str]   = set()
        page      = 1
        keep_going = True

        while keep_going and page <= _MAX_PAGES:
            # Lote de hasta _PAGE_WORKERS páginas en paralelo
            batch_pages = list(range(page, min(page + _PAGE_WORKERS, _MAX_PAGES + 1)))

            # ThreadPoolExecutor local — cloudscraper no es thread-safe entre instancias,
            # pero cada worker llama a self._fetch_url que usa self.scraper (una instancia).
            # Para paralelismo real sin conflictos creamos un scraper temporal por hilo.
            page_results: dict[int, tuple[list[dict], bool]] = {}

            def _fetch_with_own_scraper(pg: int) -> tuple[int, list[dict], bool]:
                page_key   = f"ikigai:catalog_page:{pg}"
                page_items = search_cache.get(page_key)
                if page_items is not None:
                    return pg, page_items, True

                url = (self.CATALOGO_BASE if pg == 1
                       else f"{self.CATALOGO_BASE}?pagina={pg}")
                try:
                    rate_limiter.wait(url)
                    sc   = HttpPool.get_scraper()
                    resp = sc.get(url, headers=self._headers, timeout=HTTP_TIMEOUT)
                    resp.raise_for_status()
                    soup       = BeautifulSoup(resp.text, 'html.parser')
                    items      = self._parse_page_links(soup)
                    has_next_p = self._has_next_page(soup, pg + 1)
                    if items:
                        search_cache.set(page_key, items, ttl=_PAGE_TTL)
                    return pg, items, has_next_p
                except Exception as exc:
                    logger.exception(f"Ikigai: error página {pg}: {exc}")
                    return pg, [], False

            with ThreadPoolExecutor(max_workers=_PAGE_WORKERS) as pool:
                futures = {pool.submit(_fetch_with_own_scraper, pg): pg
                           for pg in batch_pages}
                for future in as_completed(futures):
                    pg, items, has_next_p = future.result()
                    page_results[pg] = (items, has_next_p)

            # Procesar lote en orden para mantener el catálogo ordenado
            for pg in sorted(page_results):
                items, has_next_p = page_results[pg]

                if not items:
                    keep_going = False
                    break

                prev = len(results)
                for item in items:
                    if item['id'] not in seen_slugs:
                        seen_slugs.add(item['id'])
                        results.append(item)

                logger.debug(f"Ikigai: página {pg} — {len(results) - prev} nuevas "
                             f"(total: {len(results)})")

                if not has_next_p:
                    keep_going = False
                    break

            page += _PAGE_WORKERS

        if page > _MAX_PAGES:
            logger.warning(f"Ikigai: límite de {_MAX_PAGES} páginas alcanzado en catálogo")

        logger.info(f"Ikigai: catálogo con {len(results)} series")
        return results

    def _refresh_catalog_background(self) -> None:
        """
        Programa un refresco del catálogo en un thread daemon.
        Garantías:
          - Solo un thread refresca a la vez (lock de clase).
          - No se relanza si el último refresco fue hace menos de _REFRESH_COOLDOWN.
          - Si el lock está tomado, retorna inmediatamente sin bloquear.
        """
        now = time.time()
        if now - IkigaiSource._last_refresh_ts < IkigaiSource._REFRESH_COOLDOWN:
            return
        if not IkigaiSource._refresh_lock.acquire(blocking=False):
            return

        def _do() -> None:
            try:
                logger.info("Ikigai: refresco de catálogo en background")
                search_cache.delete("ikigai:catalog")
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("ikigai:catalog", catalog, ttl=_CATALOG_TTL)
                    IkigaiSource._last_refresh_ts = time.time()
                    logger.info(f"Ikigai: catálogo refrescado ({len(catalog)} series)")
            except Exception as exc:
                logger.exception(f"Ikigai: error en refresco de catálogo: {exc}")
            finally:
                IkigaiSource._refresh_lock.release()

        threading.Thread(target=_do, daemon=True).start()

    def warm_cache_sync(self) -> None:
        """
        Precarga el catálogo en background al arrancar la app.
        Llamar desde create_app() después de start_workers().
        Si el catálogo ya está en caché válida, no hace nada.
        """
        if search_cache.get("ikigai:catalog") is not None:
            logger.debug("Ikigai: catálogo ya en caché, sin precarga necesaria")
            return

        logger.info("Ikigai: iniciando precarga de catálogo en background")

        def _do() -> None:
            try:
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("ikigai:catalog", catalog, ttl=_CATALOG_TTL)
                    IkigaiSource._last_refresh_ts = time.time()
                    logger.info(f"Ikigai: precarga completada ({len(catalog)} series)")
            except Exception as exc:
                logger.exception(f"Ikigai: error en precarga: {exc}")

        threading.Thread(target=_do, daemon=True).start()

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    def search_sync(self, query: str) -> list[SearchResult]:
        """
        Búsqueda por substring en título e id.
        El catálogo se sirve desde caché (TTL 3 días).
        Si no hay caché, se construye en primer plano (solo ocurre la primera vez
        o después de 3 días sin acceso; en producción warm_cache() lo evita).
        Un refresco en background se dispara cada 6 horas como máximo.
        """
        catalog = search_cache.get("ikigai:catalog")
        if catalog is None:
            logger.info("Ikigai: descargando catálogo completo (primera vez o caché expirada)")
            catalog = self._fetch_full_catalog()
            if catalog:
                search_cache.set("ikigai:catalog", catalog, ttl=_CATALOG_TTL)
                IkigaiSource._last_refresh_ts = time.time()
        else:
            self._refresh_catalog_background()

        q = query.lower()
        return [SearchResult(id=r['id'], title=r['title'], cover=r.get('cover', ''))
                for r in (catalog or [])
                if q in r['title'].lower() or q in r['id'].lower()]

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        cache_key = f"ikigai:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return SeriesDetails(**cached)

        url  = f"{self.BASE_URL}/series/{content_id}/"
        html = self._fetch_url(url)
        soup = BeautifulSoup(html, 'html.parser')

        title_tag = soup.find('h1')
        title     = title_tag.get_text(strip=True) if title_tag else content_id

        cover     = ''
        cover_img = soup.select_one('img.w-full')
        if cover_img:
            cover = cover_img.get('src', '')

        synopsis     = ''
        synopsis_tag = soup.find('p', class_='text-gray-300')
        if synopsis_tag:
            synopsis = synopsis_tag.get_text(strip=True)
        else:
            desc_div = soup.find('div', class_='description')
            if desc_div:
                synopsis = desc_div.get_text(strip=True)

        result = SeriesDetails(title=title, cover=cover, synopsis=synopsis)
        search_cache.set(cache_key, result.model_dump())
        return result

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        cache_key = f"ikigai:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return [Chapter(**c) for c in cached]

        chapters: list[dict] = []
        page = 1

        while page <= _MAX_PAGES:
            url = f"{self.BASE_URL}/series/{content_id}/?ordenar=asc"
            if page > 1:
                url += f"&pagina={page}"

            try:
                html = self._fetch_url(url)
            except Exception as exc:
                logger.exception(f"Ikigai: error al cargar capítulos página {page} "
                             f"de '{content_id}': {exc}")
                break

            soup       = BeautifulSoup(html, 'html.parser')
            chap_items = soup.select('li.w-full a[href*="/capitulo/"]')
            if not chap_items:
                break

            for a in chap_items:
                href  = a.get('href', '')
                match = re.search(r'/capitulo/(\d+)/', href)
                if not match:
                    continue
                chap_id = match.group(1)
                num     = chap_id

                img = a.find('img')
                if img and img.get('alt'):
                    m = re.search(r'Capítulo\s+(\d+(?:\.\d+)?)', img['alt'], re.I)
                    if m:
                        num = m.group(1)
                if num == chap_id:
                    text = a.get_text(strip=True)
                    m    = re.search(r'(\d+(?:\.\d+)?)', text)
                    if m:
                        num = m.group(1)
                if num == chap_id:
                    logger.warning(f"Ikigai: no se pudo extraer número del capítulo "
                                   f"{chap_id} en '{content_id}', usando id como fallback")

                chapters.append({'number': num, 'id': chap_id})

            if not self._has_next_page(soup, page + 1):
                break
            page += 1

        if page > _MAX_PAGES:
            logger.warning(f"Ikigai: límite de {_MAX_PAGES} páginas alcanzado en capítulos "
                           f"de '{content_id}'")

        chapters.sort(key=lambda x: chapter_float_key(x['number']))
        search_cache.set(cache_key, chapters)
        return [Chapter(**c) for c in chapters]

    def get_chapter_images_sync(self, content_id: str, chapter_id: str) -> list[str]:
        cap_url = f"{self.BASE_URL}/capitulo/{chapter_id}/"
        html    = self._fetch_url(cap_url)
        soup    = BeautifulSoup(html, 'html.parser')

        seen:     set[str]  = set()
        img_urls: list[str] = []

        all_imgs = list(soup.find_all('img'))
        for noscript in soup.find_all('noscript'):
            inner = BeautifulSoup(noscript.decode_contents(), 'html.parser')
            all_imgs.extend(inner.find_all('img'))

        for img in all_imgs:
            src = (img.get('data-src') or img.get('data-lazy') or
                   img.get('data-original') or img.get('data-url') or
                   img.get('src'))
            url = normalize_image_url(src, self.BASE_URL)
            if url and url not in seen:
                seen.add(url)
                img_urls.append(url)

        # Fallback: extract from Qwik JSON (<script type="qwik/json">)
        if not img_urls:
            for script in soup.find_all('script', type='qwik/json'):
                urls = re.findall(r'https://image3\.ikigaimangas\.cloud[^"\'\\\s]+\.webp', script.string or '')
                for u in urls:
                    norm = normalize_image_url(u, self.BASE_URL)
                    if norm and norm not in seen:
                        seen.add(norm)
                        img_urls.append(norm)
                if img_urls:
                    break

        return img_urls

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str, chapter_number: str | None = None) -> str:
        img_urls = self.get_chapter_images_sync(content_id, chapter_id)

        if not img_urls:
            raise Exception(f"Ikigai: no se encontraron imágenes en capítulo {chapter_id}")

        cap_num = chapter_number or chapter_id
        dir_name = (f"cap_{chapter_to_filename(cap_num)}"
                    if cap_num.replace('.', '', 1).isdigit()
                    else f"cap_{cap_num}")
        cap_dir  = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        cap_url = f"{self.BASE_URL}/capitulo/{chapter_id}/"
        dl_headers       = {**self._headers, 'Referer': cap_url}
        downloaded_count = 0
        for i, img_url in enumerate(img_urls, start=1):
            ext      = url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                downloaded_count += 1
                continue
            try:
                with self._get_with_retry(img_url, headers=dl_headers, stream=True) as resp:
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                downloaded_count += 1
            except Exception as exc:
                logger.warning(f"Ikigai: error descargando imagen {i} "
                               f"del capítulo {chapter_id} (ignorada): {exc}")

        if downloaded_count == 0:
            raise Exception(f"Ikigai: no se pudo descargar ninguna imagen del capítulo {chapter_id}")

        return cap_dir
