#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse

import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache
from core.throttle import rate_limiter

logger = logging.getLogger(__name__)

_TIMEOUT   = 30
_MAX_PAGES = 500


class ManhwawebSource(BaseSource):
    BASE_URL = "https://www.manhwaweb.com"
    API_BASE = "https://manhwawebbackend-production.up.railway.app"
    UA       = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    _CATALOG_TTL = 60 * 60 * 24 * 3   # 3 días

    _refresh_lock    = threading.Lock()
    _last_refresh_ts = 0.0

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, **kwargs):
        rate_limiter.wait(url)
        kwargs.setdefault('timeout', _TIMEOUT)
        headers = self._headers.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> dict:
        kwargs.setdefault('headers', {})
        kwargs['headers']['Accept'] = 'application/json'
        return self._get(url, **kwargs).json()

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
                    logger.warning(f"ManhwaWeb: reintento {attempt + 1}/{retries - 1} "
                                   f"para {url[:80]}… (espera {wait:.1f}s): {exc}")
                    time.sleep(wait)
        raise last_exc

    # -----------------------------------------------------------------------
    # URL helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalize_url(src: str, base_url: str) -> str | None:
        if not src or src.startswith('data:'):
            return None
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = urljoin(base_url, src)
        # Filtrar solo placeholders obvios, no por extensión
        # (muchos CDNs sirven imágenes sin extensión o con params)
        lower = src.lower()
        if any(x in lower for x in ('loading', 'placeholder', 'blank.', 'spinner')):
            return None
        return src

    @staticmethod
    def _url_ext(url: str) -> str:
        path = urlparse(url).path
        ext  = os.path.splitext(path)[1].lstrip('.')
        # También detectar extensión en query params (ej. ?format=webp)
        if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
            m = re.search(r'[?&]format=(jpg|jpeg|png|webp)', url, re.I)
            ext = m.group(1) if m else 'jpg'
        return ext

    @staticmethod
    def _chapter_num_from_id(chapter_id: str) -> str:
        """
        Extrae el número de capítulo del chapter_id de forma robusta.
        Ej: 'lector-omnisciente-99214996766-1' → '1'
             'serie-123-5.5'                  → '5.5'
        """
        m = re.search(r'(\d+(?:\.\d+)?)$', chapter_id)
        return m.group(1) if m else chapter_id

    # -----------------------------------------------------------------------
    # Capítulos helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _dedup_sort_chapters(chapters: list[dict]) -> list[dict]:
        """Elimina duplicados por número, filtra decimales y ordena ascendentemente."""
        seen: set[str] = set()
        result: list[dict] = []
        _log = logging.getLogger(__name__)
        for ch in chapters:
            num = ch['number']
            try:
                if float(num) != int(float(num)):
                    _log.debug(f"ManhwaWeb: ignorando capítulo decimal {num!r}")
                    continue
            except (ValueError, TypeError):
                pass
            if num not in seen:
                seen.add(num)
                result.append(ch)
        result.sort(key=lambda x: float(x['number'])
                    if x['number'].replace('.', '', 1).isdigit() else 0)
        return result

    # -----------------------------------------------------------------------
    # Descarga de imágenes helper
    # -----------------------------------------------------------------------

    def _download_images(self, img_urls: list[str], cap_dir: str,
                         referer: str) -> int:
        """
        Descarga la lista de imágenes en `cap_dir`.
        Devuelve el número de fallos. El llamador decide si lanzar excepción.
        Omite imágenes que ya existen en disco.
        """
        dl_headers  = {'User-Agent': self.UA, 'Referer': referer}
        failures = 0

        for i, img_url in enumerate(img_urls, start=1):
            norm = self._normalize_url(img_url, self.BASE_URL)
            if not norm:
                continue
            ext      = self._url_ext(norm)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                continue
            try:
                with self._get_with_retry(img_url, headers=dl_headers, stream=True) as resp:
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
            except Exception as exc:
                logger.error(f"ManhwaWeb: error descargando imagen {i} ({norm}): {exc}")
                failures += 1

        return failures

    @staticmethod
    def _count_images(cap_dir: str) -> int:
        """Cuenta imágenes ya descargadas en un directorio de capítulo."""
        exts = {'.jpg', '.jpeg', '.png', '.webp'}
        return sum(
            1 for f in Path(cap_dir).iterdir()
            if f.is_file() and f.suffix.lower() in exts
        )

    # -----------------------------------------------------------------------
    # Background cache
    # -----------------------------------------------------------------------

    def warm_cache(self) -> None:
        """Precarga el catálogo en background al arrancar la app."""
        if search_cache.get("manhwaweb:catalog") is not None:
            logger.debug("ManhwaWeb: catálogo ya en caché, sin precarga necesaria")
            return

        logger.info("ManhwaWeb: iniciando precarga de catálogo en background")

        def _do() -> None:
            try:
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("manhwaweb:catalog", catalog, ttl=self._CATALOG_TTL)
            except Exception as exc:
                logger.error(f"ManhwaWeb: error en precarga: {exc}")

        threading.Thread(target=_do, daemon=True).start()

    def _refresh_catalog_background(self) -> None:
        """Refresca el catálogo en background si ha pasado suficiente tiempo."""
        now = time.time()
        if now - ManhwawebSource._last_refresh_ts < self._CATALOG_TTL:
            return
        if not ManhwawebSource._refresh_lock.acquire(blocking=False):
            return

        def _do() -> None:
            try:
                logger.info("ManhwaWeb: refresco de catálogo en background")
                search_cache.delete("manhwaweb:catalog")
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("manhwaweb:catalog", catalog, ttl=self._CATALOG_TTL)
                    ManhwawebSource._last_refresh_ts = time.time()
                    logger.info(f"ManhwaWeb: catálogo refrescado ({len(catalog)} series)")
            except Exception as exc:
                logger.error(f"ManhwaWeb: error en refresco de catálogo: {exc}")
            finally:
                ManhwawebSource._refresh_lock.release()

        threading.Thread(target=_do, daemon=True).start()

    # -----------------------------------------------------------------------
    # Búsqueda
    # -----------------------------------------------------------------------

    def _fetch_full_catalog(self) -> list[dict]:
        """
        Descarga el catálogo completo paginado desde la API en paralelo.
        Estrategia: lotes de _PAGE_WORKERS páginas en paralelo.
        """
        _PAGE_WORKERS = 8
        results:  list[dict] = []
        seen_ids: set[str]   = set()
        got_first_page       = False

        def _fetch_page(pg: int) -> list[dict]:
            url = f"{self.API_BASE}/manhwa/library?buscar=&page={pg}"
            try:
                data  = self._get_json(url)
                items = data.get('data', [])
                return items
            except Exception:
                return None

        page = 0
        while page < _MAX_PAGES:
            batch = list(range(page, min(page + _PAGE_WORKERS, _MAX_PAGES)))
            with ThreadPoolExecutor(max_workers=_PAGE_WORKERS) as pool:
                futures = {pool.submit(_fetch_page, pg): pg for pg in batch}
                results_map = {}
                for future in as_completed(futures):
                    pg = futures[future]
                    results_map[pg] = future.result()

            stop = False
            for pg in sorted(results_map):
                items = results_map[pg]
                if items is None:
                    if not got_first_page:
                        return []
                    stop = True
                    break
                if not items:
                    stop = True
                    break
                got_first_page = True
                for item in items:
                    _id = item.get('_id')
                    if not _id or _id in seen_ids:
                        continue
                    seen_ids.add(_id)
                    title = (item.get('the_real_name') or item.get('name_esp')
                             or item.get('_name') or _id)
                    results.append({'id': _id, 'title': title,
                                    'cover': item.get('_imagen', '')})
            if stop:
                break
            page += _PAGE_WORKERS

        if page >= _MAX_PAGES:
            logger.warning(f"ManhwaWeb: límite de {_MAX_PAGES} páginas alcanzado en catálogo")

        logger.info(f"ManhwaWeb: catálogo descargado con {len(results)} series")
        return results

    def search(self, query: str) -> list:
        """
        Busca en el catálogo cacheados si está disponible.
        Si no hay catálogo en caché, hace una búsqueda por scraping directa
        (rápida) y dispara la descarga del catálogo en background para
        próximas búsquedas.
        """
        cache_key = "manhwaweb:catalog"
        catalog = search_cache.get(cache_key)
        if catalog is not None:
            self._refresh_catalog_background()
            q = query.lower()
            return [r for r in catalog if q in r['title'].lower() or q in r['id'].lower()]

        # Sin catálogo en caché: búsqueda rápida por scraping + precarga en background
        logger.info("ManhwaWeb: sin catálogo en caché, usando búsqueda directa")
        self.warm_cache()
        return self._search_scrape(query)
    
    def _search_scrape(self, query: str) -> list:
        """Búsqueda mediante scraping de la página web (fallback cuando API falla)."""
        url = f"{self.BASE_URL}/?s={requests.utils.quote(query)}"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as e:
            logger.error(f"ManhwaWeb: error scraping búsqueda para '{query}': {e}")
            return []
        results = []
        # Los resultados suelen estar en elementos .media-card o .item
        for item in soup.select('.media-card, .item, .post-item'):
            a = item.find('a', href=True)
            if not a:
                continue
            href = a['href']
            # Extraer ID de la URL (ej: /manhwa/lector-omnisciente_1699214996766)
            match = re.search(r'/manhwa/([^/]+)/?$', href)
            if not match:
                continue
            content_id = match.group(1)
            title = a.get('title') or a.get_text(strip=True) or content_id
            cover = ''
            img = item.find('img')
            if img and img.get('src'):
                cover = img['src']
                if cover.startswith('//'):
                    cover = 'https:' + cover
            results.append({'id': content_id, 'title': title, 'cover': cover})
        return results

    # -----------------------------------------------------------------------
    # Detalles
    # -----------------------------------------------------------------------

    def get_details(self, content_id: str) -> dict:
        cache_key = f"manhwaweb:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        result = None
        try:
            data     = self._get_json(f"{self.API_BASE}/manhwa/see/{content_id}")
            title    = (data.get('the_real_name') or data.get('name_esp')
                        or data.get('_name') or content_id)
            cover    = data.get('_imagen', '')
            if cover and cover.startswith('//'):
                cover = 'https:' + cover
            result = {'title': title, 'cover': cover,
                      'synopsis': data.get('_sinopsis', '')}
        except Exception as exc:
            logger.warning(f"ManhwaWeb: API get_details falló para '{content_id}': {exc}, "
                           f"usando scraping")
            result = self._get_details_scrape(content_id)

        if result:
            search_cache.set(cache_key, result)
        return result or {'title': content_id, 'cover': '', 'synopsis': ''}

    def _get_details_scrape(self, content_id: str) -> dict:
        url = f"{self.BASE_URL}/manhwa/{content_id}"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as exc:
            logger.error(f"ManhwaWeb: error scraping detalles para '{content_id}': {exc}")
            return {'title': content_id, 'cover': '', 'synopsis': ''}

        title = content_id
        h2    = soup.find('h2')
        if h2:
            title = h2.get_text(strip=True)

        cover = ''
        img   = (soup.select_one('img.w-full.object-cover.aspect-defect')
                 or soup.select_one('.summary_image img'))
        if img and img.get('src'):
            cover = img['src']
            if cover.startswith('//'):
                cover = 'https:' + cover

        synopsis = ''
        desc     = soup.select_one('.summary__content, .description-summary, .entry-content')
        if desc:
            synopsis = desc.get_text(strip=True)

        return {'title': title, 'cover': cover, 'synopsis': synopsis}

    # -----------------------------------------------------------------------
    # Capítulos
    # -----------------------------------------------------------------------

    def get_chapters(self, content_id: str) -> list:
        cache_key = f"manhwaweb:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            data     = self._get_json(f"{self.API_BASE}/manhwa/see/{content_id}")
            chapters = []
            for ch in data.get('chapters', []):
                num = str(ch.get('chapter', ''))
                if num:
                    chapters.append({'number': num, 'id': f"{content_id}-{num}"})
            chapters = self._dedup_sort_chapters(chapters)
            if chapters:
                search_cache.set(cache_key, chapters)
            return chapters
        except Exception as exc:
            logger.warning(f"ManhwaWeb: API chapters falló para '{content_id}': {exc}, "
                           f"usando scraping")

        chapters = self._get_chapters_scrape(content_id)
        if chapters:
            search_cache.set(cache_key, chapters)
        return chapters

    def _get_chapters_scrape(self, content_id: str) -> list:
        url = f"{self.BASE_URL}/manhwa/{content_id}"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as exc:
            logger.error(f"ManhwaWeb: error scraping capítulos para '{content_id}': {exc}")
            return []

        chapters: list[dict] = []

        # Ruta 1: divs estructurados
        chapter_divs = soup.select('div.flex.p-2.gap-2.border-t')
        if chapter_divs:
            logger.debug(f"ManhwaWeb: capítulos via divs estructurados para '{content_id}'")
            for div in chapter_divs:
                a_tag = div.select_one('a[href*="/leer/"]')
                if not a_tag:
                    continue
                href = a_tag.get('href', '')
                m    = re.search(r'(\d+(?:\.\d+)?)$', href)
                if not m:
                    continue
                num     = m.group(1)
                chap_id = href.strip('/').split('/')[-1]
                chapters.append({'number': num, 'id': chap_id})

        # Ruta 2: fallback a cualquier enlace /leer/
        else:
            logger.debug(f"ManhwaWeb: capítulos via fallback /leer/ para '{content_id}'")
            for a in soup.select('a[href*="/leer/"]'):
                href = a.get('href', '')
                m    = re.search(r'-(\d+(?:\.\d+)?)$', href)
                if m:
                    num = m.group(1)
                    chapters.append({'number': num, 'id': f"{content_id}-{num}"})

        return self._dedup_sort_chapters(chapters)

    # -----------------------------------------------------------------------
    # Descarga de capítulo
    # -----------------------------------------------------------------------

    def download_chapter(self, content_id: str, chapter_id: str,
                         dest_folder: str) -> str:
        num         = self._chapter_num_from_id(chapter_id)
        dir_name    = (f"cap_{int(float(num)):04d}"
                       if num.replace('.', '', 1).isdigit() else f"cap_{num}")
        cap_dir     = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        # Obtener lista de imágenes desde la API
        api_url = f"{self.API_BASE}/chapters/see/{chapter_id}"
        img_urls: list[str] = []
        try:
            data         = self._get_json(api_url)
            chapter_data = data.get('chapter', {})
            img_urls     = (chapter_data.get('img')
                            or data.get('images')
                            or data.get('img')
                            or data.get('pages')
                            or [])
            if not img_urls:
                raise Exception("La API no devolvió imágenes")
        except Exception as exc:
            logger.warning(f"ManhwaWeb: API imágenes falló para '{chapter_id}': {exc}, "
                           f"usando scraping")
            return self._download_chapter_scrape(content_id, chapter_id, cap_dir)

        # Verificar si ya está completo (evita redownload de capítulos parciales)
        existing = self._count_images(cap_dir)
        if existing >= len(img_urls):
            logger.debug(f"ManhwaWeb: capítulo ya completo ({existing} imágenes): {cap_dir}")
            return cap_dir

        failures = self._download_images(img_urls, cap_dir, referer=self.BASE_URL)
        if failures:
            raise Exception(
                f"ManhwaWeb: {failures}/{len(img_urls)} imágenes fallaron "
                f"en el capítulo '{chapter_id}'"
            )
        return cap_dir

    def _download_chapter_scrape(self, content_id: str, chapter_id: str,
                                  cap_dir: str) -> str:
        num     = self._chapter_num_from_id(chapter_id)
        web_url = f"{self.BASE_URL}/leer/{content_id}-{num}"
        try:
            resp = self._get(web_url,
                             headers={'Referer': self.BASE_URL})
        except Exception as exc:
            raise Exception(f"ManhwaWeb: error al obtener página del capítulo: {exc}") from exc

        soup = BeautifulSoup(resp.text, 'html.parser')
        container = (soup.select_one('#chapter-content, .chapter-content, .reading-content')
                     or soup)

        # Deduplicar respetando orden del DOM
        seen: set[str]      = set()
        img_urls: list[str] = []

        # Recopilar todos los <img>, incluyendo los dentro de <noscript>
        # (técnica común de lazy loading donde la img real va en noscript)
        all_imgs = list(container.find_all('img'))
        for noscript in container.find_all('noscript'):
            inner = BeautifulSoup(noscript.decode_contents(), 'html.parser')
            all_imgs.extend(inner.find_all('img'))

        for img in all_imgs:
            # Priorizar data-src y variantes de lazy loading sobre src,
            # ya que src puede contener un placeholder (loading.gif, etc.)
            src = (img.get('data-src') or img.get('data-lazy') or
                   img.get('data-original') or img.get('data-url') or
                   img.get('src'))
            url = self._normalize_url(src, self.BASE_URL)
            if url and url not in seen:
                seen.add(url)
                img_urls.append(url)

        if not img_urls:
            raise Exception(f"ManhwaWeb: no se encontraron imágenes en '{chapter_id}'")

        failures = self._download_images(img_urls, cap_dir, referer=self.BASE_URL)
        if failures:
            raise Exception(
                f"ManhwaWeb: {failures}/{len(img_urls)} imágenes fallaron "
                f"en el capítulo '{chapter_id}' (scraping)"
            )
        return cap_dir