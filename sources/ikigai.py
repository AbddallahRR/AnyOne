#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import time
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache

logger = logging.getLogger(__name__)

# Timeout estándar para todas las peticiones HTTP
_TIMEOUT = 30
# Máximo de páginas al paginar (evita bucles infinitos)
_MAX_PAGES = 500


class IkigaiSource(BaseSource):
    BASE_URL      = "https://viralikigai.guildoll.info"
    CATALOGO_BASE = "https://zonaikigai.milkchoco.online/series/"
    UA            = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, **kwargs):
        kwargs.setdefault('timeout', _TIMEOUT)
        # Combinar cabeceras: las propias de la clase como base, y las que vengan en kwargs
        headers = self._headers.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _fetch_url(self, url: str, **kwargs) -> str:
        """Devuelve el texto HTML de una URL."""
        return self._get(url, **kwargs).text

    def _get_with_retry(self, url: str, retries: int = 3,
                        backoff: float = 1.0, **kwargs):
        """GET con reintentos exponenciales ante errores de red."""
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

    @staticmethod
    def _normalize_url(src: str, base_url: str) -> str | None:
        """Convierte src relativo a URL absoluta. Devuelve None si no es imagen."""
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
        """Extrae la extensión del path de una URL. Fallback a 'jpg'."""
        path = urlparse(url).path
        ext  = os.path.splitext(path)[1].lstrip('.')
        return ext if ext in {'jpg', 'jpeg', 'png', 'webp'} else 'jpg'

    # -----------------------------------------------------------------------
    # Catálogo completo (usado por search con caché)
    # -----------------------------------------------------------------------

    @staticmethod
    def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
        """
        Detecta si existe una página siguiente en la paginación.
        Busca un enlace que apunte a ?pagina=N con N > current_page,
        o un elemento con clase 'next' o texto 'Siguiente'.
        """
        # Buscar cualquier enlace que contenga 'pagina=' y extraer el número
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            match = re.search(r'[?&]pagina=(\d+)', href)
            if match:
                page_num = int(match.group(1))
                if page_num > current_page:
                    return True
            # Alternativa: texto 'siguiente' o 'next'
            if a.get_text(strip=True).lower() in ('siguiente', 'next', '→', '»'):
                return True
        return False

    def _fetch_full_catalog(self) -> list[dict]:
        """
        Descarga todas las páginas del catálogo y devuelve la lista de series.
        """
        results = []
        seen_slugs = set()
        page = 1

        while page <= _MAX_PAGES:
            url = f"{self.CATALOGO_BASE}?pagina={page}" if page > 1 else self.CATALOGO_BASE
            logger.info(f"Ikigai: descargando catálogo página {page} -> {url}")
            try:
                html = self._fetch_url(url)
            except Exception as exc:
                logger.error(f"Ikigai: error al cargar catálogo página {page}: {exc}")
                break

            soup = BeautifulSoup(html, 'html.parser')
            # Buscar enlaces a series individuales (excluir enlaces de paginación)
            links = []
            for a in soup.select('a[href^="/series/"]'):
                href = a.get('href', '')
                # Excluir enlaces que tengan '?pagina=' (paginación)
                if '?pagina=' not in href:
                    links.append(a)

            if not links:
                logger.debug(f"Ikigai: no se encontraron series en página {page}")
                # Si es la primera página y no hay series, romper
                if page == 1:
                    break
                # Si no hay series pero podría haber página siguiente, comprobamos
                if not self._has_next_page(soup, page):
                    break
                page += 1
                continue

            prev_count = len(results)
            for a in links:
                href = a.get('href', '')
                slug = href.rstrip('/').split('/')[-1]
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)

                title = a.get('title') or a.get_text(strip=True) or slug.replace('-', ' ').title()
                cover = ''
                img = a.find('img')
                if img:
                    cover = img.get('src', '')
                results.append({'id': slug, 'title': title, 'cover': cover})

            logger.info(f"Ikigai: página {page} → {len(results) - prev_count} series nuevas (total: {len(results)})")

            # Verificar si hay página siguiente
            if not self._has_next_page(soup, page):
                logger.info(f"Ikigai: no hay página siguiente, deteniendo en página {page}")
                break

            page += 1

        if page > _MAX_PAGES:
            logger.warning(f"Ikigai: se alcanzó el límite de {_MAX_PAGES} páginas en el catálogo")

        logger.info(f"Ikigai: catálogo finalizado con {len(results)} series")
        return results

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list:
        """
        Filtra el catálogo local. El catálogo completo se cachea 12h
        para evitar N peticiones HTTP por cada búsqueda.
        """
        cache_key = "ikigai:catalog"
        catalog   = search_cache.get(cache_key)
        if catalog is None:
            logger.info("Ikigai: descargando catálogo completo (primera vez o caché expirada)")
            catalog = self._fetch_full_catalog()
            search_cache.set(cache_key, catalog)

        q = query.lower()
        return [r for r in catalog
                if q in r['title'].lower() or q in r['id'].lower()]

    def get_details(self, content_id: str) -> dict:
        cache_key = f"ikigai:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        url  = f"{self.BASE_URL}/series/{content_id}/"
        html = self._fetch_url(url)
        soup = BeautifulSoup(html, 'html.parser')

        # Título
        title_tag = soup.find('h1')
        title     = title_tag.get_text(strip=True) if title_tag else content_id

        # Portada
        cover     = ''
        cover_img = soup.select_one('img.w-full')
        if cover_img:
            cover = cover_img.get('src', '')

        # Sinopsis
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

        for page in range(1, _MAX_PAGES + 1):
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
                num     = chap_id  # fallback

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

            page += 1  # noqa: intentional — for-else handled below
        else:
            logger.warning(f"Ikigai: se alcanzó el límite de {_MAX_PAGES} páginas "
                           f"de capítulos para '{content_id}'")

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

        # Número real del capítulo
        cap_num  = chapter_id
        m        = re.search(r'Capítulo\s+(\d+(?:\.\d+)?)', html, re.I)
        if m:
            cap_num = m.group(1)

        # Directorio de destino
        dir_name = (f"cap_{int(float(cap_num)):04d}"
                    if cap_num.replace('.', '', 1).isdigit()
                    else f"cap_{cap_num}")
        cap_dir  = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        # Extraer URLs de imágenes respetando el orden del DOM
        seen: set[str] = set()
        img_urls: list[str] = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            url = self._normalize_url(src, self.BASE_URL)
            if url and url not in seen:
                seen.add(url)
                img_urls.append(url)

        if not img_urls:
            raise Exception(f"Ikigai: no se encontraron imágenes en capítulo {chapter_id}")

        # Descargar con reintentos, pero sin detener todo el capítulo si una imagen falla
        dl_headers = {**self._headers, 'Referer': cap_url}
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
                logger.debug(f"Ikigai: imagen {i} descargada correctamente")
            except Exception as exc:
                # Ignorar esta imagen y continuar con la siguiente
                logger.warning(f"Ikigai: error descargando imagen {i} del capítulo {chapter_id} (ignorada): {exc}")
                continue

        if downloaded_count == 0:
            raise Exception(f"Ikigai: no se pudo descargar ninguna imagen del capítulo {chapter_id}")

        return cap_dir