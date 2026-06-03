#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache
from core.throttle import rate_limiter

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class OlympusSource(BaseSource):
    BASE_URL = "https://olympusbiblioteca.com"
    API_BASE = "https://dashboard.olympusbiblioteca.com/api"
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
        return {'User-Agent': self.UA, 'Accept': 'application/json'}

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
        if not src or src.startswith('data:'):
            return None
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = base_url + src
        # Filtrar solo placeholders obvios, no por extensión
        # (muchos CDNs sirven imágenes sin extensión o con params)
        lower = src.lower()
        if any(x in lower for x in ('loading', 'placeholder', 'blank.', 'spinner')):
            return None
        return src

    @staticmethod
    def _url_ext(url: str) -> str:
        path = urlparse(url).path          # urlparse importado al tope
        ext  = os.path.splitext(path)[1].lstrip('.')
        # También detectar extensión en query params (ej. ?format=webp)
        if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
            m = re.search(r'[?&]format=(jpg|jpeg|png|webp)', url, re.I)
            ext = m.group(1) if m else 'jpg'
        return ext

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
    # Background cache
    # -----------------------------------------------------------------------

    def warm_cache(self) -> None:
        """Precarga el catálogo en background al arrancar la app."""
        if search_cache.get("olympus:catalog") is not None:
            logger.debug("Olympus: catálogo ya en caché, sin precarga necesaria")
            return

        logger.info("Olympus: iniciando precarga de catálogo en background")

        def _do() -> None:
            try:
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("olympus:catalog", catalog, ttl=self._CATALOG_TTL)
            except Exception as exc:
                logger.error(f"Olympus: error en precarga: {exc}")

        threading.Thread(target=_do, daemon=True).start()

    def _refresh_catalog_background(self) -> None:
        """Refresca el catálogo en background si ha pasado suficiente tiempo."""
        now = time.time()
        if now - OlympusSource._last_refresh_ts < self._CATALOG_TTL:
            return
        if not OlympusSource._refresh_lock.acquire(blocking=False):
            return

        def _do() -> None:
            try:
                logger.info("Olympus: refresco de catálogo en background")
                search_cache.delete("olympus:catalog")
                catalog = self._fetch_full_catalog()
                if catalog:
                    search_cache.set("olympus:catalog", catalog, ttl=self._CATALOG_TTL)
                    OlympusSource._last_refresh_ts = time.time()
                    logger.info(f"Olympus: catálogo refrescado ({len(catalog)} series)")
            except Exception as exc:
                logger.error(f"Olympus: error en refresco de catálogo: {exc}")
            finally:
                OlympusSource._refresh_lock.release()

        threading.Thread(target=_do, daemon=True).start()

    # -----------------------------------------------------------------------
    # Búsqueda
    # -----------------------------------------------------------------------

    def _fetch_full_catalog(self) -> list[dict]:
        """
        Descarga todas las páginas del catálogo en paralelo.
        Obtiene la primera página, determina last_page, y descarga el resto
        en lotes paralelos (como ikigai).
        """
        _PAGE_WORKERS = 8
        results:    list[dict] = []
        seen_slugs: set[str]   = set()

        # Primera página para conocer last_page
        first_url = f"{self.API_BASE}/series?type=comic&direction=asc&page=1"
        try:
            data = self._get_json(first_url)
        except Exception as exc:
            logger.error(f"Olympus: error al cargar página 1: {exc}")
            return []

        first_series = data.get('data', {}).get('series', {}).get('data', [])
        if not first_series:
            return []

        last_page = data.get('data', {}).get('series', {}).get('last_page', 1)

        for s in first_series:
            slug = s.get('slug')
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                results.append({
                    'id':    slug,
                    'title': s.get('name', slug),
                    'cover': s.get('cover', ''),
                })

        if last_page <= 1:
            return results

        def _fetch_page(pg: int) -> list[dict]:
            url = f"{self.API_BASE}/series?type=comic&direction=asc&page={pg}"
            try:
                data  = self._get_json(url)
                items = data.get('data', {}).get('series', {}).get('data', [])
                return items
            except Exception as exc:
                logger.error(f"Olympus: error página {pg}: {exc}")
                return None

        pages = list(range(2, last_page + 1))
        for i in range(0, len(pages), _PAGE_WORKERS):
            batch = pages[i:i + _PAGE_WORKERS]
            with ThreadPoolExecutor(max_workers=_PAGE_WORKERS) as pool:
                futures = {pool.submit(_fetch_page, pg): pg for pg in batch}
                results_map = {}
                for future in as_completed(futures):
                    pg = futures[future]
                    results_map[pg] = future.result()

            for pg in sorted(results_map):
                items = results_map[pg]
                if items is None:
                    continue
                for s in items:
                    slug = s.get('slug')
                    if slug and slug not in seen_slugs:
                        seen_slugs.add(slug)
                        results.append({
                            'id':    slug,
                            'title': s.get('name', slug),
                            'cover': s.get('cover', ''),
                        })

        logger.info(f"Olympus: catálogo descargado con {len(results)} series")
        return results

    def search(self, query: str) -> list:
        cache_key = "olympus:catalog"
        catalog   = search_cache.get(cache_key)
        if catalog is not None:
            self._refresh_catalog_background()
            q = query.lower()
            return [r for r in catalog if q in r['title'].lower() or q in r['id'].lower()]

        # Sin catálogo: lo precargamos en background y mientras tanto
        # devolvemos la primera página filtrada por query si la API lo soporta
        logger.info("Olympus: sin catálogo, precargando en background")
        self.warm_cache()

        # Intentar búsqueda directa en API
        try:
            data = self._get_json(
                f"{self.API_BASE}/series?type=comic&direction=asc&page=1"
            )
            series = data.get('data', {}).get('series', {}).get('data', [])
            q = query.lower()
            return [{
                'id': s['slug'],
                'title': s.get('name', s['slug']),
                'cover': s.get('cover', ''),
            } for s in series if s.get('slug') and (
                q in s.get('name', '').lower() or q in s['slug'].lower()
            )]
        except Exception:
            return []

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