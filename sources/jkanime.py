#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import logging
import os
import re
import subprocess
import time

import requests
import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache

logger = logging.getLogger(__name__)

# Prioridad de servidores (índice menor = mayor prioridad)
_SERVER_PRIORITY = [
    'Mediafire', 'Mp4upload', 'Mega',
    'Streamwish', 'VOE', 'Vidhide', 'Mixdrop', 'Streamtape', 'Doodstream',
]

# Timeouts
_TIMEOUT_HTTP  = 30
_TIMEOUT_CURL  = 1800   # 30 min por intento de descarga


class JkanimeSource(BaseSource):
    BASE_URL = "https://jkanime.net"
    UA       = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, referer: str | None = None, **kwargs):
        headers = {**self._headers}
        if referer:
            headers['Referer'] = referer
        kwargs.setdefault('timeout', _TIMEOUT_HTTP)
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, data=None, referer: str | None = None):
        headers = {
            **self._headers,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type':     'application/x-www-form-urlencoded',
        }
        if referer:
            headers['Referer'] = referer
        resp = self.scraper.post(url, headers=headers, data=data, timeout=_TIMEOUT_HTTP)
        resp.raise_for_status()
        return resp

    # -----------------------------------------------------------------------
    # Parsing helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_csrf_token(html: str) -> str:
        patterns = [
            r'<input[^>]+name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
            r'var\s+token\s*=\s*["\']([^"\']+)["\']',
            r'_token["\']?\s*:\s*["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                return m.group(1)
        return ''

    @staticmethod
    def _decode_remote(encoded: str) -> str:
        """Decodifica un campo remote en base64 URL-safe."""
        return base64.b64decode(
            encoded.replace('-', '+').replace('_', '/')
        ).decode('utf-8')

    def _parse_servers_from_table(self, soup: BeautifulSoup) -> list[dict]:
        """Extrae servidores desde la tabla de descargas del HTML del episodio."""
        servers = []
        table = soup.select_one('.download table, .download tbody')
        if not table:
            return servers
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            server_name = cells[0].get_text(strip=True)
            link_tag    = cells[-1].find('a')
            if not link_tag or not link_tag.get('href'):
                continue
            m = re.search(r'/d/([^/]+)/', link_tag['href'])
            if m:
                servers.append({'server': server_name, 'slug': m.group(1), 'remote': ''})
        return servers

    def _parse_servers_from_js(self, html: str) -> list[dict]:
        """Fallback: extrae servidores desde variables JS del HTML."""
        # Intento 1: var servers = [...]
        for pattern in [
            r'var\s+servers\s*=\s*(\[.*?\])\s*;',
            r'servers\s*=\s*(\[.*?\])\s*;',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                raw = m.group(1)
                raw = raw.replace("'", '"')
                raw = re.sub(r',\s*[}\]]', lambda x: x.group(0)[1:], raw)
                raw = re.sub(r'\s+', ' ', raw)
                try:
                    return [s for s in __import__('json').loads(raw) if s.get('server')]
                except Exception:
                    pass

        # Intento 2: regex directo sobre pares clave-valor
        servers = []
        for m in re.finditer(r'"remote":"([^"]+)","slug":"([^"]+)","server":"([^"]+)"', html):
            servers.append({'server': m.group(3), 'remote': m.group(1), 'slug': m.group(2)})
        return servers

    # -----------------------------------------------------------------------
    # Descarga de archivo — helpers por servidor
    # -----------------------------------------------------------------------

    def _download_stream(self, url: str, filepath: str,
                         referer: str | None = None) -> str:
        """
        Descarga un MP4 via requests con streaming.
        Elimina el archivo si falla a mitad.
        """
        headers = {**self._headers}
        if referer:
            headers['Referer'] = referer

        with requests.get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            logger.debug(f"Progreso: {downloaded/total*100:.1f}%")
        return filepath

    def _download_curl(self, url: str, filepath: str,
                       referer: str = 'https://www.mp4upload.com/',
                       origin: str  = 'https://www.mp4upload.com') -> str:
        """
        Descarga con curl. Soporta reanudación (-C -).
        Reintenta una vez si el archivo queda incompleto.
        """
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        cmd = [
            'curl', '-L', '-k', '-C', '-',
            '-o', filepath,
            '--fail', '--progress-bar',
            '--connect-timeout', '60',
            '--max-time', str(_TIMEOUT_CURL),
            '--header', f'User-Agent: {self.UA}',
            '--header', f'Referer: {referer}',
            '--header', f'Origin: {origin}',
            '--header', 'Accept: */*',
            url,
        ]

        # Tamaño esperado (para verificar integridad)
        expected: int | None = None
        try:
            head = self.scraper.head(url, headers=self._headers, timeout=_TIMEOUT_HTTP)
            if head.status_code == 200:
                expected = int(head.headers.get('content-length', 0)) or None
        except Exception:
            pass

        for attempt in range(2):
            try:
                subprocess.run(cmd, check=True, timeout=_TIMEOUT_CURL)
            except subprocess.TimeoutExpired:
                logger.warning(f"curl timeout en intento {attempt + 1}")
                if attempt == 1:
                    raise Exception("Descarga incompleta tras dos intentos (timeout)")
                continue
            except subprocess.CalledProcessError as exc:
                raise Exception(f"curl error: {exc}") from exc

            # Verificar tamaño
            actual = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            if expected and actual < expected:
                logger.warning(f"Archivo incompleto ({actual}/{expected} bytes), reintentando…")
                continue
            break

        return filepath

    def _resolve_mediafire(self, encoded: str) -> str:
        """Devuelve la URL directa de descarga de Mediafire."""
        page_url = self._decode_remote(encoded)
        logger.debug(f"Mediafire: página remota {page_url}")
        html = self._get(page_url).text

        m = re.search(r'<a[^>]+id="downloadButton"[^>]+href="([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'https://download[^"\']+\.mp4', html)
        if m:
            return m.group(0)
        raise Exception("No se encontró enlace de descarga en Mediafire")

    def _resolve_mp4upload(self, encoded: str) -> str:
        """Obtiene la URL directa de Mp4upload via yt-dlp."""
        embed_url = self._decode_remote(encoded)
        logger.debug(f"Mp4upload: embed URL {embed_url}")
        try:
            result = subprocess.run(
                ['yt-dlp', '-g', '--no-warnings', embed_url],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except FileNotFoundError:
            raise Exception("yt-dlp no está instalado")

        if result.returncode != 0:
            raise Exception(f"yt-dlp falló: {result.stderr.strip()}")
        url = result.stdout.strip().split('\n')[0]
        if not url.startswith('http'):
            raise Exception(f"yt-dlp devolvió URL inválida: {url!r}")
        return url

    def _resolve_generic(self, slug: str) -> str:
        """Intenta obtener una URL directa de un servidor genérico (jkplayers)."""
        candidate = f"https://c1.jkplayers.com/d/{slug}/"
        resp = self.scraper.get(
            candidate, headers=self._headers, timeout=_TIMEOUT_HTTP, allow_redirects=True
        )
        final_url = resp.url
        ct = resp.headers.get('content-type', '')
        if final_url.endswith('.mp4') and 'video/mp4' in ct:
            return final_url

        # Buscar enlace mp4 o botón de descarga en la página de destino
        html = resp.text
        m = re.search(r'<a[^>]+id="downloadButton"[^>]+href="([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'(https?://[^"\']+\.mp4)', html)
        if m:
            return m.group(1)
        raise Exception(f"No se pudo extraer enlace directo para slug {slug!r}")

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list:
        encoded = requests.utils.quote(query)
        url     = f"{self.BASE_URL}/buscar/{encoded}"
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.error(f"Jkanime search error: {exc}")
            return []

        pattern = re.compile(r'href="https?://jkanime\.net/([a-z0-9][a-z0-9-]+)/"')
        skip    = {'buscar', 'anime', 'ver', 'capitulo', 'tag', 'genero', 'categoria'}
        slugs   = {m.group(1) for m in pattern.finditer(html) if m.group(1) not in skip}

        return [
            {
                'id':    slug,
                'title': slug.replace('-', ' ').title(),
                'cover': f"https://cdn.jkdesa.com/assets/images/animes/image/{slug}.jpg",
            }
            for slug in slugs
        ]

    def get_details(self, content_id: str) -> dict:
        fallback = {
            'title':    content_id,
            'cover':    f"https://cdn.jkdesa.com/assets/images/animes/image/{content_id}.jpg",
            'synopsis': '',
        }
        try:
            html = self._get(f"{self.BASE_URL}/{content_id}/").text
        except Exception as exc:
            logger.error(f"Jkanime get_details error para '{content_id}': {exc}")
            return fallback

        soup         = BeautifulSoup(html, 'html.parser')
        title_elem   = soup.select_one('.anime_info h3') or soup.select_one('h1.title, h1')
        synopsis_elem = soup.select_one('p.scroll')

        return {
            'title':    title_elem.get_text(strip=True) if title_elem else content_id,
            'cover':    fallback['cover'],
            'synopsis': synopsis_elem.get_text(strip=True) if synopsis_elem else '',
        }

    def get_chapters(self, content_id: str) -> list:
        cache_key = f"jkanime:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return cached

        main_url = f"{self.BASE_URL}/{content_id}/"
        try:
            resp = self._get(main_url)
        except Exception as exc:
            logger.error(f"Jkanime get_chapters error para '{content_id}': {exc}")
            return []

        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')

        # Obtener serie_id
        serie_id = None
        guardar  = soup.select_one('#guardar-anime')
        if guardar and guardar.get('data-anime'):
            serie_id = guardar['data-anime']
        if not serie_id:
            for script in soup.find_all('script'):
                if script.string:
                    m = re.search(r'data-anime=["\']?(\d+)', script.string)
                    if m:
                        serie_id = m.group(1)
                        break
        if not serie_id:
            logger.error(f"Jkanime: no se pudo obtener serie_id para '{content_id}'")
            return []

        logger.debug(f"Jkanime: serie_id={serie_id} para '{content_id}'")

        token    = self._get_csrf_token(html)
        if not token:
            logger.warning("Jkanime: no se pudo obtener token CSRF, continuando sin él")
        post_data = {'_token': token} if token else {}

        # Primera página AJAX
        try:
            ajax_resp = self._post(
                f"{self.BASE_URL}/ajax/episodes/{serie_id}/1",
                data=post_data, referer=main_url,
            )
            data = ajax_resp.json()
        except Exception as exc:
            logger.error(f"Jkanime: error en AJAX para '{content_id}': {exc}")
            return []

        total = data.get('total', 0)
        if total > 0:
            chapters = [{'number': str(i), 'id': str(i)} for i in range(1, total + 1)]
            logger.info(f"Jkanime: {len(chapters)} capítulos para '{content_id}' (total directo)")
            search_cache.set(cache_key, chapters)
            return chapters

        # Fallback: recorrer páginas
        chapters: list[dict] = []
        last_page = data.get('last_page', 1)

        for ep in data.get('data', []):
            num = ep.get('number')
            if num is not None:
                chapters.append({'number': str(num), 'id': str(num)})

        for page in range(2, last_page + 1):
            try:
                r    = self._post(
                    f"{self.BASE_URL}/ajax/episodes/{serie_id}/{page}",
                    data=post_data, referer=main_url,
                )
                page_data = r.json()
            except Exception as exc:
                logger.warning(f"Jkanime: error en página {page} para '{content_id}': {exc}")
                continue

            for ep in page_data.get('data', []):
                num = ep.get('number')
                if num is not None:
                    chapters.append({'number': str(num), 'id': str(num)})

        chapters.sort(key=lambda x: int(x['number']))
        logger.info(f"Jkanime: {len(chapters)} capítulos para '{content_id}' (paginado)")
        search_cache.set(cache_key, chapters)
        return chapters

    def download_chapter(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        cap_url = f"{self.BASE_URL}/{content_id}/{chapter_id}/"
        html    = self._get(cap_url).text
        soup    = BeautifulSoup(html, 'html.parser')

        # Resolver lista de servidores
        servers = self._parse_servers_from_table(soup)
        if not servers:
            servers = self._parse_servers_from_js(html)
        if not servers:
            raise Exception("No se encontraron servidores de descarga")

        servers.sort(key=lambda s: (
            _SERVER_PRIORITY.index(s['server'])
            if s['server'] in _SERVER_PRIORITY else len(_SERVER_PRIORITY)
        ))

        # Ruta de destino común — usar float primero para soportar decimales (ej. "12.5")
        cap_num  = int(float(chapter_id)) if chapter_id.replace('.', '', 1).isdigit() else 0
        filename = f"{content_id}_{cap_num:03d}.mp4"
        filepath = os.path.join(dest_folder, filename)
        os.makedirs(dest_folder, exist_ok=True)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.info(f"Jkanime: archivo ya existe, reutilizando: {filepath}")
            return filepath

        for server in servers:
            name    = server.get('server', '')
            remote  = server.get('remote', '')
            slug    = server.get('slug', '')

            logger.info(f"Jkanime: probando servidor {name!r}")
            try:
                if name == 'Mediafire' and remote:
                    direct = self._resolve_mediafire(remote)
                    return self._download_stream(direct, filepath)

                elif name == 'Mp4upload' and remote:
                    direct = self._resolve_mp4upload(remote)
                    return self._download_curl(
                        direct, filepath,
                        referer='https://www.mp4upload.com/',
                        origin='https://www.mp4upload.com',
                    )

                elif slug:
                    direct = self._resolve_generic(slug)
                    return self._download_stream(direct, filepath,
                                                 referer=self.BASE_URL)

            except Exception as exc:
                logger.warning(f"Jkanime: servidor {name!r} falló: {exc}")
                # Limpiar archivo parcial (vacío o corrupto) antes del siguiente servidor
                if os.path.exists(filepath):
                    os.remove(filepath)
                continue

        raise Exception(f"No se pudo descargar el capítulo {chapter_id} desde ningún servidor")

    def get_stream_url(self, content_id: str, chapter_id: str) -> str | None:
        """
        Streaming no implementado para jkanime.
        Devuelve None intencionalmente; la app usa download_chapter en su lugar.
        """
        return None