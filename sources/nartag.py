#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

import cloudscraper
import requests
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class NartagSource(BaseSource):
    BASE_URL = "https://nartag.com"
    CDN      = "https://nartag.com/wp-content/uploads"
    UA       = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

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
        # Fusionar headers por defecto con los proporcionados en la llamada
        headers = self._headers.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, **kwargs):
        kwargs.setdefault('timeout', _TIMEOUT)
        headers = self._headers.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self.scraper.post(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

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
                    logger.warning(f"Nartag: reintento {attempt + 1}/{retries - 1} "
                                   f"para {url[:80]}… (espera {wait:.1f}s): {exc}")
                    time.sleep(wait)
        raise last_exc

    # -----------------------------------------------------------------------
    # URL helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalize_url(src: str, base_url: str) -> str | None:
        """
        Normaliza una URL de imagen a absoluta.
        Elimina sufijos de thumbnail WordPress (ej. -300x400.jpg → .jpg).
        Descarta URLs que no sean imágenes o sean banners.
        """
        if not src:
            return None
        src = src.strip()
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = urljoin(base_url, src)
        if not re.search(r'\.(jpg|jpeg|png|webp)(\?.*)?$', src, re.I):
            return None
        # Eliminar dimensiones de thumbnail WordPress: -300x400.jpg → .jpg
        src = re.sub(r'-\d+x\d+(\.\w+)$', r'\1', src)
        if 'banner' in src.lower():
            return None
        return src

    @staticmethod
    def _url_ext(url: str) -> str:
        path = urlparse(url).path
        ext  = os.path.splitext(path)[1].lstrip('.')
        return ext if ext in {'jpg', 'jpeg', 'png', 'webp'} else 'jpg'

    @staticmethod
    def _best_cover_url(img_tag, base_url: str = '') -> str:
        """
        Elige la URL de mayor resolución desde srcset, data-srcset o src.
        Elimina sufijos de thumbnail WordPress del resultado.
        """
        if not img_tag:
            return ''
        srcset = img_tag.get('srcset', '') or img_tag.get('data-srcset', '')
        if srcset:
            candidates = []
            for part in srcset.split(','):
                tokens = part.strip().split()
                if not tokens:
                    continue
                w = (int(tokens[1].rstrip('w'))
                     if len(tokens) > 1 and tokens[1].endswith('w') else 0)
                candidates.append((w, tokens[0]))
            if candidates:
                best = max(candidates, key=lambda x: x[0])[1]
                return re.sub(r'-\d+x\d+(\.\w+)$', r'\1', best)
        src = img_tag.get('data-src') or img_tag.get('src', '')
        return re.sub(r'-\d+x\d+(\.\w+)$', r'\1', src) if src else ''

    @staticmethod
    def _count_images(cap_dir: str) -> int:
        exts = {'.jpg', '.jpeg', '.png', '.webp'}
        return sum(
            1 for f in Path(cap_dir).iterdir()
            if f.is_file() and f.suffix.lower() in exts
        )

    # -----------------------------------------------------------------------
    # Búsqueda
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list:
        cache_key = f"nartag:search:{query}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        encoded = requests.utils.quote(query)
        url     = f"{self.BASE_URL}/?s={encoded}&post_type=wp-manga"
        try:
            # Usar self.scraper (cloudscraper) para evitar bloqueos de Cloudflare
            html = self._get(url).text
        except Exception as exc:
            logger.error(f"Nartag: error en búsqueda '{query}': {exc}")
            return []

        soup    = BeautifulSoup(html, 'html.parser')
        results: list[dict] = []
        seen:   set[str]    = set()

        for thumb in soup.select('.tab-thumb.c-image-hover'):
            a = thumb.find('a', href=True)
            if not a:
                continue
            m = re.search(r'/manga/([^/]+)/', a['href'])
            if not m:
                continue
            slug = m.group(1)
            if slug in seen:
                continue
            seen.add(slug)
            title = a.get('title', '') or slug.replace('-', ' ').title()
            cover = self._best_cover_url(thumb.find('img'), self.BASE_URL)
            results.append({'id': slug, 'title': title, 'cover': cover})

        search_cache.set(cache_key, results)
        return results

    # -----------------------------------------------------------------------
    # Detalles
    # -----------------------------------------------------------------------

    def get_details(self, content_id: str) -> dict:
        cache_key = f"nartag:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}/manga/{content_id}/"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as exc:
            logger.error(f"Nartag: error obteniendo detalles para '{content_id}': {exc}")
            return {'title': content_id, 'cover': '', 'synopsis': ''}

        # Título
        title     = content_id
        title_tag = soup.find('h1')
        if title_tag:
            for badge in title_tag.find_all('span'):
                badge.decompose()
            title = title_tag.get_text(strip=True)

        # Portada — intenta varios selectores en orden
        cover = ''
        for selector in [
            '.tab-thumb img',
            '.tab-thumb.c-image-hover img',
            '.summary_image img',
            'img.img-responsive',
            'img.wp-post-image',
        ]:
            img = soup.select_one(selector)
            if img:
                cover = self._best_cover_url(img, self.BASE_URL)
                if cover:
                    break

        if cover:
            logger.debug(f"Nartag: portada encontrada para '{content_id}': {cover}")
        else:
            logger.warning(f"Nartag: no se encontró portada para '{content_id}'")

        # Sinopsis
        synopsis = ''
        summary_header = soup.find('h5', string=lambda x: x and 'summary' in x.lower())
        if summary_header:
            parent = summary_header.find_parent('div')
            if parent:
                content_div = parent.find('div', recursive=False)
                if content_div:
                    synopsis = content_div.get_text(strip=True)
        if not synopsis:
            summary_div = soup.select_one('.summary__content, .description-summary')
            if summary_div:
                synopsis = summary_div.get_text(strip=True)

        result = {'title': title, 'cover': cover, 'synopsis': synopsis}
        search_cache.set(cache_key, result)
        return result

    # -----------------------------------------------------------------------
    # Capítulos
    # -----------------------------------------------------------------------

    def get_chapters(self, content_id: str) -> list:
        cache_key = f"nartag:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        ajax_url = f"{self.BASE_URL}/manga/{content_id}/ajax/chapters/"
        headers  = {
            **self._headers,
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f"{self.BASE_URL}/manga/{content_id}/",
        }
        try:
            resp = self.scraper.post(ajax_url, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.error(f"Nartag: error obteniendo capítulos para '{content_id}': {exc}")
            return []

        pattern   = re.compile(
            r'href="https://nartag\.com/manga/[^"]+/(?:capitulos/)?(capitulo-\d+[^"]*)/"'
        )
        cap_slugs = set(pattern.findall(html))
        if not cap_slugs:
            logger.warning(f"Nartag: no se encontraron capítulos para '{content_id}'")
            return []

        def _extract_num(slug: str) -> float:
            m = re.search(r'capitulo-(\d+(?:\.\d+)?)', slug)
            return float(m.group(1)) if m else 0.0

        chapters = []
        for slug in sorted(cap_slugs, key=_extract_num):
            m      = re.search(r'capitulo-(\d+(?:\.\d+)?)', slug)
            number = m.group(1) if m else slug
            chapters.append({'number': number, 'id': slug})

        search_cache.set(cache_key, chapters)
        return chapters

    # -----------------------------------------------------------------------
    # Descarga de capítulo
    # -----------------------------------------------------------------------

    def download_chapter(self, content_id: str, chapter_id: str,
                         dest_folder: str) -> str:
        m       = re.search(r'capitulo-(\d+(?:\.\d+)?)', chapter_id)
        cap_num = m.group(1) if m else chapter_id
        dir_name = (f"cap_{int(float(cap_num)):04d}"
                    if cap_num.replace('.', '', 1).isdigit()
                    else f"cap_{cap_num}")
        cap_dir  = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        cap_url = f"{self.BASE_URL}/manga/{content_id}/capitulos/{chapter_id}/"
        try:
            html = self._get(cap_url,
                             headers={'Referer': f"{self.BASE_URL}/manga/{content_id}/"}).text
        except Exception as exc:
            raise Exception(f"Nartag: error HTTP al obtener capítulo '{chapter_id}': {exc}") from exc

        soup = BeautifulSoup(html, 'html.parser')

        # Extraer imágenes respetando orden del DOM
        container = soup.select_one('.reading-content')
        imgs      = (container.find_all('img') if container
                     else soup.find_all('img', class_='wp-manga-chapter-img'))
        if not imgs:
            # Fallback: cualquier img con extensión de imagen
            imgs = [img for img in soup.find_all('img')
                    if re.search(r'\.(jpg|jpeg|png|webp)', img.get('src', ''), re.I)]

        seen: set[str]      = set()
        img_urls: list[str] = []
        for img in imgs:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            url = self._normalize_url(src, self.BASE_URL)
            if url and url not in seen:
                seen.add(url)
                img_urls.append(url)

        if not img_urls:
            raise Exception(f"Nartag: no se encontraron imágenes en '{chapter_id}'")

        # Verificar completitud real antes de redownload
        existing = self._count_images(cap_dir)
        if existing >= len(img_urls):
            logger.debug(f"Nartag: capítulo ya completo ({existing} imágenes): {cap_dir}")
            return cap_dir

        # Descargar — lanza en el primer fallo (capítulo completo o nada)
        dl_headers = {'User-Agent': self.UA, 'Referer': cap_url}
        for i, img_url in enumerate(img_urls, start=1):
            ext      = self._url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                continue
            try:
                resp = self._get_with_retry(img_url, headers=dl_headers, stream=True)
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(8192):
                        f.write(chunk)
            except Exception as exc:
                raise Exception(
                    f"Nartag: error descargando imagen {i}/{len(img_urls)} "
                    f"del capítulo '{chapter_id}': {exc}"
                ) from exc

        return cap_dir