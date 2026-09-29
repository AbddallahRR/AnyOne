#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# --- IGNORE ---

import logging
import re
from urllib.parse import quote as _url_quote

from bs4 import BeautifulSoup

from core.disk_cache import search_cache
from core.html_utils import collect_reader_images, normalize_url
from core.models import Chapter, SearchResult, SeriesDetails
from core.utils import count_images_in_dir

from . import BaseSource
from .common import HttpClientMixin, MangaDownloadHelper

logger = logging.getLogger(__name__)



class ManhwawebSource(HttpClientMixin, BaseSource):
    type = 'manga'
    label = 'ManhwaWeb'
    BASE_URL = "https://www.manhwaweb.com"
    API_BASE = "https://manhwawebbackend-production.up.railway.app"

    # -----------------------------------------------------------------------
    # URL helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _chapter_num_from_id(chapter_id: str) -> str:
        """
        Extrae el número de capítulo del chapter_id de forma robusta.
        Ej: 'lector-omnisciente-99214996766-1' → '1'
             'serie-123-5.5'                  → '5.5'
        """
        m = re.search(r'([\d._]+)$', chapter_id)
        return m.group(1) if m else chapter_id

    # -----------------------------------------------------------------------
    # Capítulos helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _dedup_sort_chapters(chapters: list[dict]) -> list[dict]:
        seen: set[str] = set()
        result: list[dict] = []
        for ch in chapters:
            num = ch['number']
            if num not in seen:
                seen.add(num)
                result.append(ch)
        def _sort_key(ch: dict) -> float:
            san = ch['number'].replace('_', '.')
            try:
                return float(san)
            except ValueError:
                return 0
        result.sort(key=_sort_key)
        return result

    # -----------------------------------------------------------------------
    # Búsqueda
    # -----------------------------------------------------------------------

    def search_sync(self, query: str) -> list[SearchResult]:
        """
        Busca en vivo vía API de ManhwaWeb con el query como parámetro.
        Si la API falla, hace scraping de la página de búsqueda.
        """
        try:
            data = self._get_json(
                f"{self.API_BASE}/manhwa/library?buscar={_url_quote(query)}&page=1"
            )
            items = data.get('data', [])
            if items:
                results = []
                for item in items:
                    _id = item.get('_id')
                    if not _id:
                        continue
                    title = (item.get('the_real_name') or item.get('name_esp')
                             or item.get('_name') or _id)
                    cover = item.get('_imagen', '')
                    results.append(SearchResult(id=_id, title=title, cover=cover))
                return results
        except Exception as exc:
            logger.warning(f"ManhwaWeb: API search falló para '{query}': {exc}")

        return self._search_scrape(query)

    def _search_scrape(self, query: str) -> list[SearchResult]:
        """Búsqueda mediante scraping de la página web (fallback cuando API falla)."""
        url = f"{self.BASE_URL}/?s={_url_quote(query)}"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as e:
            logger.exception(f"ManhwaWeb: error scraping búsqueda para '{query}': {e}")
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
                cover = normalize_url(img['src'], self.BASE_URL)
            results.append(SearchResult(id=content_id, title=title, cover=cover))
        return results

    # -----------------------------------------------------------------------
    # Detalles
    # -----------------------------------------------------------------------

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        cache_key = f"manhwaweb:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return SeriesDetails(**cached)

        result = None
        try:
            data     = self._get_json(f"{self.API_BASE}/manhwa/see/{content_id}")
            title    = (data.get('the_real_name') or data.get('name_esp')
                        or data.get('_name') or content_id)
            cover    = normalize_url(data.get('_imagen', ''), self.BASE_URL)
            result = SeriesDetails(title=title, cover=cover,
                      synopsis=data.get('_sinopsis', ''))
        except Exception as exc:
            logger.warning(f"ManhwaWeb: API get_details falló para '{content_id}': {exc}, "
                           f"usando scraping")
            result = self._get_details_scrape(content_id)

        if result:
            search_cache.set(cache_key, result.model_dump())
        return result or SeriesDetails(title=content_id)

    def _get_details_scrape(self, content_id: str) -> SeriesDetails:
        url = f"{self.BASE_URL}/manhwa/{content_id}"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as exc:
            logger.exception(f"ManhwaWeb: error scraping detalles para '{content_id}': {exc}")
            return SeriesDetails(title=content_id)

        title = content_id
        h2    = soup.find('h2')
        if h2:
            title = h2.get_text(strip=True)

        cover = ''
        img   = (soup.select_one('img.w-full.object-cover.aspect-defect')
                 or soup.select_one('.summary_image img'))
        if img and img.get('src'):
            cover = normalize_url(img['src'], self.BASE_URL)

        synopsis = ''
        desc     = soup.select_one('.summary__content, .description-summary, .entry-content')
        if desc:
            synopsis = desc.get_text(strip=True)

        return SeriesDetails(title=title, cover=cover, synopsis=synopsis)

    # -----------------------------------------------------------------------
    # Capítulos
    # -----------------------------------------------------------------------

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        cache_key = f"manhwaweb:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return [Chapter(**c) for c in cached]

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
            return [Chapter(**c) for c in chapters]
        except Exception as exc:
            logger.warning(f"ManhwaWeb: API chapters falló para '{content_id}': {exc}, "
                           f"usando scraping")

        chapters = self._get_chapters_scrape(content_id)
        if chapters:
            search_cache.set(cache_key, chapters)
        return [Chapter(**c) for c in chapters]

    def _get_chapters_scrape(self, content_id: str) -> list:
        url = f"{self.BASE_URL}/manhwa/{content_id}"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as exc:
            logger.exception(f"ManhwaWeb: error scraping capítulos para '{content_id}': {exc}")
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
                m    = re.search(r'([\d._]+)$', href)
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
                m    = re.search(r'-([\d._]+)$', href)
                if m:
                    num = m.group(1)
                    chapters.append({'number': num, 'id': f"{content_id}-{num}"})

        return self._dedup_sort_chapters(chapters)

    # -----------------------------------------------------------------------
    # Streaming (obtener URLs de imágenes sin descargar)
    # -----------------------------------------------------------------------

    def get_chapter_images_sync(self, content_id: str, chapter_id: str) -> list[str]:
        api_url = f"{self.API_BASE}/chapters/see/{chapter_id}"
        try:
            data         = self._get_json(api_url)
            chapter_data = data.get('chapter', {})
            img_urls     = (chapter_data.get('img')
                            or data.get('images')
                            or data.get('img')
                            or data.get('pages')
                            or [])
            if img_urls:
                return img_urls
        except Exception as exc:
            logger.debug(f'ManhwaWeb: API falló para {content_id}/{chapter_id}: {exc}, usando scraping')

        num     = self._chapter_num_from_id(chapter_id)
        web_url = f"{self.BASE_URL}/leer/{content_id}-{num}"
        try:
            resp = self._get(web_url, headers={'Referer': self.BASE_URL})
        except Exception as exc:
            logger.warning(f'ManhwaWeb: error obteniendo pagina de lectura para {content_id}/{num}: {exc}')
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        return collect_reader_images(soup, self.BASE_URL)

    # -----------------------------------------------------------------------
    # Descarga de capítulo
    # -----------------------------------------------------------------------

    def download_chapter_sync(self, content_id: str, chapter_id: str,
                         dest_folder: str, chapter_number: str | None = None,
                         progress_cb=None) -> str:
        num = chapter_number or self._chapter_num_from_id(chapter_id)
        cap_dir = MangaDownloadHelper.make_chapter_dir(dest_folder, num)

        img_urls = self.get_chapter_images_sync(content_id, chapter_id)
        if not img_urls:
            raise Exception(
                f"ManhwaWeb: no se encontraron imágenes para '{content_id}/{chapter_id}'"
            )

        existing = count_images_in_dir(cap_dir)
        if existing >= len(img_urls):
            logger.debug(f"ManhwaWeb: capítulo ya completo ({existing} imágenes): {cap_dir}")
            return cap_dir

        dl_headers = {'User-Agent': self.UA, 'Referer': self.BASE_URL}
        failures = MangaDownloadHelper.download_images(
            img_urls, cap_dir, dl_headers, self._get_with_retry, progress_cb,
        )
        if failures:
            raise Exception(
                f"ManhwaWeb: {failures}/{len(img_urls)} imágenes fallaron "
                f"en el capítulo '{chapter_id}'"
            )
        return cap_dir
