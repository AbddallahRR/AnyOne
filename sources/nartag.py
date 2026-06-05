#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import cloudscraper
import requests
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache
from core.models import Chapter, SearchResult, SeriesDetails
from core.throttle import rate_limiter

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class NartagSource(BaseSource):
    BASE_URL   = "https://nartag.com"
    READER_URL = "https://lector.nartag.com"
    UA         = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

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
                    logger.warning(
                        f"Nartag: reintento {attempt + 1}/{retries - 1} "
                        f"para {url[:80]}… (espera {wait:.1f}s): {exc}"
                    )
                    time.sleep(wait)
        raise last_exc

    # -----------------------------------------------------------------------
    # URL helpers
    # -----------------------------------------------------------------------

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
    def _best_cover_url(img_tag, base_url: str = '') -> str:
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
    # Lector: hacer POST al authorize y extraer imágenes del manga
    # -----------------------------------------------------------------------

    def _get_reader_url(self, cap_url: str) -> tuple[str, dict]:
        """
        Replica el flujo del form POST automático:
        1. Obtiene el HTML del capítulo y extrae los campos del form rk_madara_redirect
        2. Hace POST a /wp-json/rk/v1/authorize con esos campos
        3. Devuelve (url_final_del_lector, fields) para usarlos como referer y contexto
        """
        try:
            html = self._get(cap_url).text
        except Exception as exc:
            raise Exception(f"Nartag: error al obtener página del capítulo: {exc}") from exc

        soup = BeautifulSoup(html, 'html.parser')
        form = soup.find('form', id='rk_madara_redirect')
        if not form:
            raise Exception(
                f"Nartag: no se encontró el form de redirección en '{cap_url}'"
            )

        fields = {
            inp['name']: inp.get('value', '')
            for inp in form.find_all('input', {'type': 'hidden'})
            if inp.get('name')
        }
        action       = form.get('action', f"{self.READER_URL}/wp-json/rk/v1/authorize")
        redirect_url = fields.get('redirect_url', '')

        if not redirect_url:
            raise Exception(
                f"Nartag: no se encontró redirect_url en el form de '{cap_url}'"
            )

        logger.debug(f"Nartag: form fields → {fields}")

        try:
            rate_limiter.wait(action)
            resp = self.scraper.post(
                action,
                data=fields,
                headers={
                    **self._headers,
                    'Referer':      cap_url,
                    'Origin':       self.BASE_URL,
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                timeout=_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise Exception(
                f"Nartag: error en POST a authorize '{action}': {exc}"
            ) from exc

        final_url = resp.url
        logger.info(f"Nartag: URL final del lector tras authorize → {final_url}")
        return final_url, fields

    def _extract_manga_images(self, reader_url: str, referer: str) -> list[str]:
        """
        Descarga la página del lector (ya autenticada vía cookie de sesión
        en self.scraper) y extrae las imágenes reales del manga.

        Las imágenes del manga están en:
          nartag.com/wp-content/uploads/WP-manga/data/...
        y NO tienen sufijo de thumbnail WordPress (-NNNxNNN).
        """
        try:
            rate_limiter.wait(reader_url)
            resp = self.scraper.get(
                reader_url,
                headers={**self._headers, 'Referer': referer},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            raise Exception(
                f"Nartag: error al obtener lector '{reader_url}': {exc}"
            ) from exc

        soup     = BeautifulSoup(html, 'html.parser')
        img_urls: list[str] = []
        seen:     set[str]  = set()

        def _is_manga_image(url: str) -> bool:
            if not url:
                return False
            parsed = urlparse(url)
            # Las imágenes reales vienen de nartag.com, no del lector
            if parsed.netloc not in ('nartag.com', 'www.nartag.com'):
                return False
            # Deben estar en la ruta de datos del manga
            if 'wp-content/uploads/WP-manga/data/' not in parsed.path:
                return False
            # Sin sufijo de thumbnail (-768x432, etc.)
            if re.search(r'-\d+x\d+\.', parsed.path):
                return False
            # Extensión válida
            if not re.search(r'\.(jpg|jpeg|png|webp|gif)$', parsed.path, re.I):
                return False
            return True

        for img in soup.find_all('img'):
            src = (
                img.get('src') or img.get('data-src') or
                img.get('data-original') or img.get('data-lazy-src') or ''
            ).strip()
            if _is_manga_image(src) and src not in seen:
                seen.add(src)
                img_urls.append(src)

        logger.info(f"Nartag: {len(img_urls)} imágenes del manga en '{reader_url}'")
        return img_urls

    # -----------------------------------------------------------------------
    # Búsqueda
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list[SearchResult]:
        cache_key = f"nartag:search:{query}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return [SearchResult(**r) if isinstance(r, dict) else r for r in cached]

        encoded = requests.utils.quote(query)
        url     = f"{self.BASE_URL}/?s={encoded}&post_type=wp-manga"
        try:
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
            results.append(SearchResult(id=slug, title=title, cover=cover))

        if results:
            search_cache.set(cache_key, [r.model_dump() for r in results])
        else:
            logger.warning(
                f"Nartag: búsqueda '{query}' devolvió 0 resultados — no se cachea"
            )

        return results

    # -----------------------------------------------------------------------
    # Detalles
    # -----------------------------------------------------------------------

    def get_details(self, content_id: str) -> SeriesDetails:
        cache_key = f"nartag:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return SeriesDetails(**cached)

        url = f"{self.BASE_URL}/manga/{content_id}/"
        try:
            soup = BeautifulSoup(self._get(url).text, 'html.parser')
        except Exception as exc:
            logger.error(f"Nartag: error obteniendo detalles para '{content_id}': {exc}")
            return SeriesDetails(title=content_id)

        title     = content_id
        title_tag = soup.find('h1')
        if title_tag:
            for badge in title_tag.find_all('span'):
                badge.decompose()
            title = title_tag.get_text(strip=True)

        cover = ''
        for selector in [
            '.tab-thumb img', '.tab-thumb.c-image-hover img',
            '.summary_image img', 'img.img-responsive', 'img.wp-post-image',
        ]:
            img = soup.select_one(selector)
            if img:
                cover = self._best_cover_url(img, self.BASE_URL)
                if cover:
                    break

        synopsis    = ''
        summary_div = soup.select_one('.summary__content, .description-summary')
        if summary_div:
            synopsis = summary_div.get_text(strip=True)

        result = SeriesDetails(title=title, cover=cover, synopsis=synopsis)
        search_cache.set(cache_key, result.model_dump())
        return result

    # -----------------------------------------------------------------------
    # Capítulos — via AJAX POST
    # -----------------------------------------------------------------------

    def get_chapters(self, content_id: str) -> list[Chapter]:
        cache_key = f"nartag:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return [Chapter(**c) for c in cached]

        ajax_url = f"{self.BASE_URL}/manga/{content_id}/ajax/chapters/"
        headers  = {
            **self._headers,
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f"{self.BASE_URL}/manga/{content_id}/",
        }
        try:
            rate_limiter.wait(ajax_url)
            resp = self.scraper.post(ajax_url, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.error(
                f"Nartag: error obteniendo capítulos para '{content_id}': {exc}"
            )
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
            try:
                if float(number) != int(float(number)):
                    logger.debug(f"Nartag: ignorando capítulo decimal {number!r} en '{content_id}'")
                    continue
            except (ValueError, TypeError):
                pass
            chapters.append({'number': number, 'id': slug})

        search_cache.set(cache_key, chapters)
        return [Chapter(**c) for c in chapters]

    # -----------------------------------------------------------------------
    # Descarga de capítulo
    # -----------------------------------------------------------------------

    def download_chapter(self, content_id: str, chapter_id: str,
                         dest_folder: str) -> str:
        m       = re.search(r'capitulo-(\d+(?:\.\d+)?)', chapter_id)
        cap_num = m.group(1) if m else chapter_id
        dir_name = (
            f"cap_{int(float(cap_num)):04d}"
            if cap_num.replace('.', '', 1).isdigit()
            else f"cap_{cap_num}"
        )
        cap_dir = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        # ── 1. URL canónica del capítulo ─────────────────────────────────────
        cap_url = f"{self.BASE_URL}/manga/{content_id}/capitulos/{chapter_id}/"

        # ── 2. POST al authorize → obtener URL del lector con cookie de sesión
        reader_url, _ = self._get_reader_url(cap_url)

        # ── 3. Extraer imágenes del manga desde la página del lector ─────────
        img_urls = self._extract_manga_images(reader_url, referer=cap_url)
        if not img_urls:
            raise Exception(
                f"Nartag: no se encontraron imágenes del manga en '{reader_url}'"
            )

        # ── 4. Saltar si ya está completo ────────────────────────────────────
        existing = self._count_images(cap_dir)
        if existing >= len(img_urls):
            logger.debug(
                f"Nartag: capítulo ya completo ({existing} imágenes): {cap_dir}"
            )
            return cap_dir

        # ── 5. Descargar ─────────────────────────────────────────────────────
        dl_headers = {'User-Agent': self.UA, 'Referer': reader_url}
        for i, img_url in enumerate(img_urls, start=1):
            ext      = self._url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                continue
            try:
                with self._get_with_retry(img_url, headers=dl_headers, stream=True) as resp:
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
            except Exception as exc:
                raise Exception(
                    f"Nartag: error descargando imagen {i}/{len(img_urls)} "
                    f"del capítulo '{chapter_id}': {exc}"
                ) from exc

        logger.info(
            f"Nartag: capítulo '{chapter_id}' descargado ({len(img_urls)} imágenes)"
        )
        return cap_dir