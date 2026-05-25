#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class OlympusSource(BaseSource):
    BASE_URL = "https://olympusbiblioteca.com"
    API_BASE = "https://dashboard.olympusbiblioteca.com/api"
    UA       = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA, 'Accept': 'application/json'}

    def _get(self, url: str, **kwargs):
        kwargs.setdefault('timeout', _TIMEOUT)
        headers = self._headers.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> dict:
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
                    logger.warning(f"Olympus: reintento {attempt + 1}/{retries - 1} "
                                   f"para {url[:80]}… (espera {wait:.1f}s): {exc}")
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
        return src

    @staticmethod
    def _url_ext(url: str) -> str:
        path = urlparse(url).path          # urlparse importado al tope
        ext  = os.path.splitext(path)[1].lstrip('.')
        return ext if ext in {'jpg', 'jpeg', 'png', 'webp'} else 'jpg'

    @staticmethod
    def _count_images(cap_dir: str) -> int:
        exts = {'.jpg', '.jpeg', '.png', '.webp'}
        return sum(
            1 for f in Path(cap_dir).iterdir()
            if f.is_file() and f.suffix.lower() in exts
        )

    # -----------------------------------------------------------------------
    # Slug helpers
    # -----------------------------------------------------------------------

    def _api_slug(self, slug: str) -> str:
        """Elimina el prefijo 'comic-' si existe (para la API)."""
        return slug[5:] if slug.startswith('comic-') else slug

    def _full_slug(self, slug: str) -> str:
        """Agrega el prefijo 'comic-' si no existe (para la URL web)."""
        return slug if slug.startswith('comic-') else f"comic-{slug}"

    # -----------------------------------------------------------------------
    # Búsqueda
    # -----------------------------------------------------------------------

    def _fetch_full_catalog(self) -> list[dict]:
        """
        Descarga todas las páginas del catálogo.
        Devuelve lista vacía si falla antes de obtener cualquier resultado,
        para evitar cachear un catálogo incompleto por error de red.
        """
        results:    list[dict] = []
        seen_slugs: set[str]   = set()
        got_first_page         = False
        page                   = 1

        while True:
            url = f"{self.API_BASE}/series?type=comic&direction=asc&page={page}"
            try:
                data   = self._get_json(url)
                series = data.get('data', {}).get('series', {}).get('data', [])
                if not series:
                    break
                got_first_page = True
                for s in series:
                    slug = s.get('slug')
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)
                    results.append({
                        'id':    slug,
                        'title': s.get('name', slug),
                        'cover': s.get('cover', ''),
                    })
                last_page = data.get('data', {}).get('series', {}).get('last_page', 1)
                if page >= last_page:
                    break
                page += 1
            except Exception as exc:
                logger.error(f"Olympus: error al cargar catálogo página {page}: {exc}")
                if not got_first_page:
                    return []   # no cachear catálogo vacío por error de red
                break

        logger.info(f"Olympus: catálogo descargado con {len(results)} series")
        return results

    def search(self, query: str) -> list:
        cache_key = "olympus:catalog"
        catalog   = search_cache.get(cache_key)
        if catalog is None:
            logger.info("Olympus: descargando catálogo completo (primera vez o caché expirada)")
            catalog = self._fetch_full_catalog()
            if catalog:                         # no cachear catálogo vacío
                search_cache.set(cache_key, catalog)

        q = query.lower()
        return [r for r in (catalog or [])
                if q in r['title'].lower() or q in r['id'].lower()]

    # -----------------------------------------------------------------------
    # Detalles
    # -----------------------------------------------------------------------

    def get_details(self, content_id: str) -> dict:
        cache_key = f"olympus:details:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self.API_BASE}/series/{self._api_slug(content_id)}"
        try:
            data     = self._get_json(url).get('data', {})
            result   = {
                'title':    data.get('name', content_id),
                'cover':    data.get('cover', ''),
                'synopsis': data.get('synopsis', ''),
            }
            search_cache.set(cache_key, result)
            return result
        except Exception as exc:
            logger.error(f"Olympus: error obteniendo detalles de '{content_id}': {exc}")
            return {'title': content_id, 'cover': '', 'synopsis': ''}

    # -----------------------------------------------------------------------
    # Capítulos
    # -----------------------------------------------------------------------

    def get_chapters(self, content_id: str) -> list:
        cache_key = f"olympus:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        api_slug = self._api_slug(content_id)
        chapters: list[dict] = []
        page     = 1

        while True:
            url = f"{self.API_BASE}/series/{api_slug}/chapters?page={page}"
            try:
                data  = self._get_json(url, headers={'Referer': self.BASE_URL})
                items = data.get('data', [])
                if not items:
                    break
                for ch in items:
                    num = str(ch.get('name', ''))
                    if num:
                        chapters.append({'number': num, 'id': str(ch.get('id', ''))})
                last_page = data.get('meta', {}).get('last_page', 1)
                if page >= last_page:
                    break
                page += 1
            except Exception as exc:
                logger.error(f"Olympus: error obteniendo capítulos de '{content_id}': {exc}")
                break

        chapters.sort(
            key=lambda x: float(x['number'])
            if x['number'].replace('.', '', 1).isdigit() else 0
        )

        # Solo cachear si obtuvimos capítulos — evita cachear [] por error de red
        if chapters:
            search_cache.set(cache_key, chapters)
            logger.debug(f"Olympus: {len(chapters)} capítulos para '{content_id}'")
        else:
            logger.warning(f"Olympus: sin capítulos para '{content_id}' (¿error de red?)")

        return chapters

    # -----------------------------------------------------------------------
    # Descarga de capítulo
    # -----------------------------------------------------------------------

    def download_chapter(self, content_id: str, chapter_id: str,
                         dest_folder: str) -> str:
        full_slug = self._full_slug(content_id)
        cap_url   = f"{self.BASE_URL}/capitulo/{chapter_id}/{full_slug}"
        headers   = {'Referer': self.BASE_URL}

        html = self._get_with_retry(cap_url, headers=headers).text

        # Localizar URL del payload JSON
        payload_url: str | None = None
        for pattern in [
            r'<link\s+rel="preload"\s+as="fetch"\s+href="([^"]+)"',
            r'(https?://[^"\']+_payload\.json[^"\']*)',
            r'data-src="([^"]+_payload\.json[^"]*)"',
        ]:
            m = re.search(pattern, html)
            if m:
                payload_url = m.group(1)
                break
        if not payload_url:
            raise Exception(f"Olympus: no se encontró payload JSON para capítulo '{chapter_id}'")
        if payload_url.startswith('/'):
            payload_url = self.BASE_URL + payload_url

        payload = self._get_with_retry(payload_url, headers=headers).json()

        # Número del capítulo: usar chapter_id como base, refinar desde payload si es posible.
        # Buscamos el primer string numérico que aparezca DESPUÉS de una clave reconocible,
        # con fallback al propio chapter_id para evitar tomar cualquier número del JSON.
        cap_num = str(chapter_id)
        for item in payload:
            if isinstance(item, str) and item.replace('.', '', 1).isdigit():
                cap_num = item
                break

        dir_name = (f"cap_{int(float(cap_num)):04d}"
                    if cap_num.replace('.', '', 1).isdigit()
                    else f"cap_{cap_num}")
        cap_dir  = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        # Extraer URLs de imágenes con deduplicación (respeta orden del payload)
        seen:     set[str]      = set()
        img_urls: list[str]     = []
        for item in payload:
            if not isinstance(item, str):
                continue
            url = self._normalize_url(item, self.BASE_URL)
            if url and url not in seen:
                seen.add(url)
                img_urls.append(url)

        if not img_urls:
            raise Exception(f"Olympus: no se encontraron imágenes en el payload de '{chapter_id}'")

        # Verificar completitud antes de redownload
        existing = self._count_images(cap_dir)
        if existing >= len(img_urls):
            logger.debug(f"Olympus: capítulo ya completo ({existing} imágenes): {cap_dir}")
            return cap_dir

        # Descargar — lanza en el primer fallo (capítulo completo o nada)
        dl_headers = {'User-Agent': self.UA, 'Referer': cap_url}
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
                    f"Olympus: error descargando imagen {i}/{len(img_urls)} "
                    f"del capítulo '{chapter_id}': {exc}"
                ) from exc

        return cap_dir