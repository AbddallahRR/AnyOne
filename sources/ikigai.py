#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import threading
import time
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache

logger = logging.getLogger(__name__)

_TIMEOUT   = 30
_MAX_PAGES = 500


class IkigaiSource(BaseSource):
    BASE_URL      = "https://visorikigai.yomod.xyz"
    CATALOGO_BASE = "https://visorikigai.yomod.xyz/series/"
    UA            = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    # Lock y timestamp a nivel de clase: compartidos entre todas las instancias/workers
    _refresh_lock    = threading.Lock()
    _last_refresh_ts = 0.0
    _REFRESH_COOLDOWN = 3600  # segundos entre refrescos en background (1 hora)

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, **kwargs):
        kwargs.setdefault('timeout', _TIMEOUT)
        # Extraer headers de kwargs y fusionarlos con los propios en un único dict.
        # Pasar 'headers' dos veces a scraper.get() causa: "got multiple values for keyword argument 'headers'"
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

    @staticmethod
    def _normalize_url(src: str, base_url: str) -> str | None:
        if not src:
            return None
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = base_url + src
        if not re.search(r'\.(jpg|jpeg|png|webp)(\?.*)?$', src, re.I):
            return None
        if 'banner' in src.lower():
            return None
        return src

    @staticmethod
    def _url_ext(url: str) -> str:
        path = urlparse(url).path
        ext  = os.path.splitext(path)[1].lstrip('.')
        return ext if ext in {'jpg', 'jpeg', 'png', 'webp'} else 'jpg'

    # -----------------------------------------------------------------------
    # Catálogo
    # -----------------------------------------------------------------------

    @staticmethod
    def _has_next_page(soup: BeautifulSoup, next_page: int) -> bool:
        """Detecta si existe un enlace a la página siguiente (cualquier formato de href)."""
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

            # Prioridad para el título:
            # 1. <h3> dentro del card (contiene solo el título)
            # 2. alt de la imagen (también contiene solo el título)
            # 3. atributo title del <a>
            # 4. fallback al slug humanizado
            # Nunca usar a.get_text() — incluye géneros, contadores y estado
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

            # Portada: src de la primera <img> dentro del card
            cover = ''
            img_tag = a.find('img')
            if img_tag:
                cover = img_tag.get('src', '')

            items.append({'id': slug, 'title': title, 'cover': cover})
        return items

    def _fetch_full_catalog(self) -> list[dict]:
        """
        Descarga el catálogo completo página por página.
        Cada página se cachea individualmente — un refresco futuro solo
        descarga las páginas cuyo caché haya expirado.
        """
        results:    list[dict] = []
        seen_slugs: set[str]   = set()
        page = 1

        while page <= _MAX_PAGES:
            page_key    = f"ikigai:catalog_page:{page}"
            page_items  = search_cache.get(page_key)
            has_next    = True  # asumir que hay siguiente hasta comprobarlo

            if page_items is None:
                # Página no cacheada — descargar
                url = (self.CATALOGO_BASE if page == 1
                       else f"{self.CATALOGO_BASE}?pagina={page}")
                try:
                    html = self._fetch_url(url)
                except Exception as exc:
                    logger.error(f"Ikigai: error al cargar catálogo página {page}: {exc}")
                    break

                soup       = BeautifulSoup(html, 'html.parser')
                page_items = self._parse_page_links(soup)
                has_next   = self._has_next_page(soup, page + 1)

                if not page_items:
                    logger.debug(f"Ikigai: página {page} sin series — fin del catálogo")
                    break

                search_cache.set(page_key, page_items)

            prev = len(results)
            for item in page_items:
                if item['id'] not in seen_slugs:
                    seen_slugs.add(item['id'])
                    results.append(item)

            logger.debug(f"Ikigai: página {page} — {len(results) - prev} nuevas "
                         f"(total: {len(results)})")

            if not has_next:
                break
            page += 1

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
            return  # otro thread ya está refrescando

        def _do() -> None:
            try:
                logger.info("Ikigai: refresco de catálogo en background")
                # Eliminar caché global para que _fetch_full_catalog
                # re-descargue las páginas cuyo caché de página haya expirado
                search_cache.delete("ikigai:catalog")
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("ikigai:catalog", catalog)
                    IkigaiSource._last_refresh_ts = time.time()
                    logger.info(f"Ikigai: catálogo refrescado ({len(catalog)} series)")
            except Exception as exc:
                logger.error(f"Ikigai: error en refresco de catálogo: {exc}")
            finally:
                IkigaiSource._refresh_lock.release()

        threading.Thread(target=_do, daemon=True).start()

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list:
        """
        Búsqueda por substring en título e id (no por palabras exactas, para
        que "solo lev" encuentre "Solo Leveling").
        El catálogo se cachea 12h; un refresco en background se dispara como
        máximo una vez por hora cuando el catálogo ya está en caché.
        """
        catalog = search_cache.get("ikigai:catalog")
        if catalog is None:
            logger.info("Ikigai: descargando catálogo completo (primera vez o caché expirada)")
            catalog = self._fetch_full_catalog()
            if catalog:
                search_cache.set("ikigai:catalog", catalog)
                IkigaiSource._last_refresh_ts = time.time()
        else:
            # Catálogo disponible: refrescar en background si toca
            self._refresh_catalog_background()

        q = query.lower()
        return [r for r in (catalog or [])
                if q in r['title'].lower() or q in r['id'].lower()]

    def get_details(self, content_id: str) -> dict:
        cache_key = f"ikigai:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

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

        result = {'title': title, 'cover': cover, 'synopsis': synopsis}
        search_cache.set(cache_key, result)
        return result

    def get_chapters(self, content_id: str) -> list:
        cache_key = f"ikigai:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        chapters: list[dict] = []
        page = 1

        while page <= _MAX_PAGES:
            url = f"{self.BASE_URL}/series/{content_id}/?ordenar=asc"
            if page > 1:
                url += f"&pagina={page}"

            try:
                html = self._fetch_url(url)
            except Exception as exc:
                logger.error(f"Ikigai: error al cargar capítulos página {page} "
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

        chapters.sort(
            key=lambda x: float(x['number'])
            if x['number'].replace('.', '', 1).isdigit() else 0
        )
        search_cache.set(cache_key, chapters)
        return chapters

    def download_chapter(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        cap_url  = f"{self.BASE_URL}/capitulo/{chapter_id}/"
        html     = self._fetch_url(cap_url)
        soup     = BeautifulSoup(html, 'html.parser')

        cap_num  = chapter_id
        m        = re.search(r'Capítulo\s+(\d+(?:\.\d+)?)', html, re.I)
        if m:
            cap_num = m.group(1)

        dir_name = (f"cap_{int(float(cap_num)):04d}"
                    if cap_num.replace('.', '', 1).isdigit()
                    else f"cap_{cap_num}")
        cap_dir  = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        seen:     set[str]      = set()
        img_urls: list[str]     = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            url = self._normalize_url(src, self.BASE_URL)
            if url and url not in seen:
                seen.add(url)
                img_urls.append(url)

        if not img_urls:
            raise Exception(f"Ikigai: no se encontraron imágenes en capítulo {chapter_id}")

        dl_headers      = {**self._headers, 'Referer': cap_url}
        downloaded_count = 0
        for i, img_url in enumerate(img_urls, start=1):
            ext      = self._url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                downloaded_count += 1
                continue
            try:
                resp = self._get_with_retry(img_url, headers=dl_headers, stream=True)
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