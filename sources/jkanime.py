#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from urllib.parse import quote as _url_quote
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from core.disk_cache import search_cache
from core.http_pool import HTTP_TIMEOUT, HttpPool
from core.models import Chapter, EpisodeLink, EpisodeLinks, SearchResult, SeriesDetails, chapter_to_filename
from core.throttle import rate_limiter

from . import BaseSource
from .common import HttpClientMixin

logger = logging.getLogger(__name__)

# Prioridad de servidores (índice menor = mayor prioridad)
_SERVER_PRIORITY = [
    'Mediafire', 'Mp4upload', 'Mixdrop',
    'Streamwish', 'Vidhide', 'Mega',
    'VOE', 'Streamtape', 'Doodstream',
]

# Servidores que soportan streaming directo (iframe embebible)
_STREAM_SERVERS = {'streamwish', 'voe', 'vidhide', 'mixdrop', 'streamtape', 'doodstream'}

# Cabeceras exigidas por el CDN de Mp4upload (sin Referer/Origin responde 403)
_MP4UPLOAD_REFERER = 'https://www.mp4upload.com/'
_MP4UPLOAD_ORIGIN  = 'https://www.mp4upload.com'

# Timeouts
_TIMEOUT_CURL = 1800   # 30 min por intento de descarga


def _split_packed_args(expr: str) -> list[str]:
    """Divide los argumentos de un eval(function(...)('...',a,c,k,0,{})) respetando strings y paréntesis."""
    parts: list[str] = []
    depth, cur, in_str = 0, '', None
    i = 0
    while i < len(expr):
        ch = expr[i]
        if in_str is not None:
            cur += ch
            if ch == '\\':
                i += 2 if i + 1 < len(expr) else 1
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "'\"":
            in_str, cur = ch, cur + ch
            i += 1
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
        i += 1
    if cur.strip():
        parts.append(cur)
    return parts


def _unpack_packed_js(html: str) -> list[str]:
    """Desofusca bloques `eval(function(p,a,c,k,e,d){...return p}('...',a,c,k.split('|'),0,{}))`
    (Dean Edwards packer). Devuelve cada bloque decodificado, no ejecuta nada."""
    results: list[str] = []
    pos = 0
    while True:
        idx = html.find("return p}('", pos)
        if idx < 0:
            break
        parts = _split_packed_args(html[idx + 10: idx + 30000])
        if len(parts) >= 4:
            p = parts[0].strip()
            if p.startswith("'") and p.endswith("'"):
                p = p[1:-1].replace("\\'", "'")
            try:
                a = int(parts[1].strip())
                c = int(parts[2].strip())
            except ValueError:
                pos = idx + 10
                continue
            k = parts[3].strip()
            if k.startswith("'") and k.endswith("'"):
                k = k[1:-1].replace("\\'", "'")
            k_list = k.split('|')

            def _packed_key(i: int) -> str:
                s = ''
                while True:
                    r = i % a
                    i //= a
                    s = (chr(r + 29) if r > 35 else '0123456789abcdefghijklmnopqrstuvwxyz'[r]) + s
                    if i == 0:
                        break
                return s

            for i in range(c):
                key = _packed_key(i)
                val = k_list[i] if i < len(k_list) else key
                p = re.sub(
                    r'(?<![A-Za-z0-9_])' + re.escape(key) + r'(?![A-Za-z0-9_])',
                    lambda m, v=val: v,
                    p,
                )
            results.append(p)
        pos = idx + 10
    return results


class JkanimeSource(HttpClientMixin, BaseSource):
    type = 'anime'
    label = 'JKanime'
    BASE_URL = "https://jkanime.net"
    _episode_html_cache: OrderedDict[str, str] = OrderedDict()
    _cache_lock = threading.Lock()
    _CACHE_MAX = 24

    def __init__(self):
        super().__init__()
        self.scraper = HttpPool.get_scraper()

    # -----------------------------------------------------------------------
    # Parsing helpers
    # -----------------------------------------------------------------------

    def _fetch_episode_html(self, content_id: str, chapter_id: str) -> str:
        cache_key = f"{content_id}/{chapter_id}"
        with self._cache_lock:
            cached = self._episode_html_cache.get(cache_key)
            if cached is not None:
                self._episode_html_cache.move_to_end(cache_key)
                return cached
        cap_url = f"{self.BASE_URL}/{content_id}/{chapter_id}/"
        html = self._get(cap_url).text
        with self._cache_lock:
            self._episode_html_cache[cache_key] = html
            while len(self._episode_html_cache) > self._CACHE_MAX:
                self._episode_html_cache.popitem(last=False)
        return html

    def invalidate_download_cache(self, content_id: str | None = None, chapter_id: str | None = None) -> None:
        """Invalida la caché de HTML de episodios (toda o una entrada)."""
        with self._cache_lock:
            if content_id and chapter_id:
                self._episode_html_cache.pop(f"{content_id}/{chapter_id}", None)
            else:
                self._episode_html_cache.clear()

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

    @staticmethod
    def _normalize_variant(lang: str | int | None) -> str:
        """Normaliza el campo lang a 'SUB' o 'DUB'."""
        token = str(lang or '').lower().replace(' ', '')
        if any(k in token for k in ('dub', 'lat', 'esp', 'cast')):
            return 'DUB'
        return 'SUB'

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
                servers.append({
                    'server':  server_name,
                    'slug':    m.group(1),
                    'remote':  '',
                    'variant': 'SUB',
                })
        return servers

    def _parse_servers_from_js(self, html: str) -> list[dict]:
        """
        Extrae servidores desde variables JS del HTML.
        Ahora también preserva el campo lang para separar SUB/DUB.
        """
        # Intento 1: var servers = [...]
        for pattern in [
            r'var\s+servers\s*=\s*(\[.*?\])\s*;',
            r'servers\s*=\s*(\[.*?\])\s*;',
        ]:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                raw = m.group(1)
                raw = raw.replace("'", '"')
                raw = re.sub(r',\s*([}\]])', r'\1', raw)
                raw = re.sub(r'\s+', ' ', raw)
                try:
                    parsed = json.loads(raw)
                    result = []
                    for s in parsed:
                        if not s.get('server'):
                            continue
                        result.append({
                            'server':  s.get('server', ''),
                            'remote':  s.get('remote', ''),
                            'slug':    s.get('slug', ''),
                            'variant': self._normalize_variant(s.get('lang')),
                        })
                    return result
                except Exception as exc:
                    logger.debug('Jkanime: fallo JSON en _parse_servers_from_js: %s, usando regex', exc)

        # Intento 2: regex directo sobre pares clave-valor
        servers = []
        for m in re.finditer(
            r'"remote":"([^"]+)","slug":"([^"]+)","server":"([^"]+)"(?:.*?"lang":"([^"]*)")?',
            html,
        ):
            servers.append({
                'server':  m.group(3),
                'remote':  m.group(1),
                'slug':    m.group(2),
                'variant': self._normalize_variant(m.group(4)),
            })
        return servers

    def _parse_iframe_urls(self, html: str) -> list[str]:
        """
        Extrae URLs de iframes embebidos desde patrones video[N] = "..." del HTML.
        Equivalente al extractVideoIframeUrls del JS de referencia.
        """
        urls = []
        for m in re.finditer(r"video\[\d+\]\s*=\s*['\"][\s\S]*?src=['\"]([^'\"]+)['\"]", html):
            url = m.group(1)
            if url and url.startswith('http'):
                urls.append(url)
        return urls

    # -----------------------------------------------------------------------
    # Descarga de archivo — helpers por servidor
    # -----------------------------------------------------------------------

    def _download_stream(self, url: str, filepath: str,
                         referer: str | None = None, progress_cb=None) -> str:
        """
        Descarga un MP4 via requests con streaming.
        Elimina el archivo si falla a mitad.
        """
        headers = {**self._headers}
        if referer:
            headers['Referer'] = referer

        _cb_throttle = [0.0]
        _cb_interval  = 0.5

        def _emit(downloaded: int, total: int | None) -> None:
            if not progress_cb:
                return
            now = time.monotonic()
            if now - _cb_throttle[0] >= _cb_interval:
                _cb_throttle[0] = now
                progress_cb(downloaded, total, 'Descargando video')

        with HttpPool.get_session().get(url, headers=headers, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0)) or None
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            logger.debug(f"Progreso: {downloaded/total*100:.1f}%")
                        _emit(downloaded, total)
        return filepath

    def _run_curl_with_progress(self, cmd: list[str], filepath: str,
                                expected: int | None, progress_cb, timeout: int) -> None:
        """Ejecuta curl (Popen) y reporta progreso muestreando el tamaño del archivo."""
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    rc = proc.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        proc.kill()
                        proc.wait()
                        raise subprocess.TimeoutExpired(cmd, timeout)
                    if progress_cb:
                        size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                        progress_cb(size, expected, 'Descargando video')
        finally:
            if proc.poll() is None:
                proc.kill()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, cmd)

    def _download_curl(self, url: str, filepath: str,
                       referer: str = 'https://www.mp4upload.com/',
                       origin: str  = 'https://www.mp4upload.com',
                       progress_cb=None) -> str:
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
            head = self.scraper.head(
                url,
                headers={**self._headers, 'Referer': referer, 'Origin': origin},
                timeout=HTTP_TIMEOUT,
            )
            if head.status_code == 200:
                expected = int(head.headers.get('content-length', 0)) or None
        except Exception:
            pass

        for attempt in range(2):
            try:
                self._run_curl_with_progress(cmd, filepath, expected, progress_cb, _TIMEOUT_CURL)
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

            # Verificar que el archivo es un video real (magic bytes MP4: ftyp en offset 4)
            if actual < 10240:
                logger.warning(f"Archivo demasiado pequeño ({actual} bytes), probablemente no es video")
                if os.path.exists(filepath):
                    os.remove(filepath)
                raise Exception(f"Descarga inválida: archivo de {actual} bytes no es un video válido")
            try:
                with open(filepath, 'rb') as f:
                    magic = f.read(12)
            except (OSError, IOError):
                break
            if len(magic) >= 8 and magic[4:8] != b'ftyp':
                logger.warning(f"Archivo no es MP4 válido (magic: {magic[:8]!r})")
                os.remove(filepath)
                raise Exception("Descarga inválida: el archivo no tiene formato MP4")

            break

        return filepath

    def _resolve_mediafire(self, encoded: str) -> str:
        """Devuelve la URL directa de descarga de Mediafire."""
        page_url = self._decode_remote(encoded)
        logger.debug(f"Mediafire: página remota {page_url}")
        resp = self._get(page_url)
        if resp.status_code >= 400:
            raise Exception(f"Mediafire devolvió HTTP {resp.status_code}")
        html = resp.text

        m = re.search(r'<a[^>]+id="downloadButton"[^>]+href="([^"]+)"', html)
        if m:
            return m.group(1)
        m = re.search(r'https://download[^"\']+\.mp4', html)
        if m:
            return m.group(0)
        raise Exception("No se encontró enlace de descarga en Mediafire")

    def _resolve_mp4upload(self, encoded: str) -> str:
        """Obtiene la URL directa de Mp4upload via yt-dlp.

        El CDN de Mp4upload exige cabeceras Referer/Origin; sin ellas
        responde HTTP 403. La URL extraída (token de corta vida) se valida
        con un GET de rango pequeño usando esas cabeceras, porque el CDN no
        siempre responde a HEAD.
        """
        embed_url = self._decode_remote(encoded)
        logger.debug(f"Mp4upload: embed URL {embed_url}")
        try:
            result = subprocess.run(
                ['yt-dlp', '-g', '--no-warnings',
                 '--referer', _MP4UPLOAD_REFERER,
                 '--add-header', f'Origin:{_MP4UPLOAD_ORIGIN}',
                 embed_url],
                capture_output=True, text=True, timeout=60, check=False,
            )
        except FileNotFoundError:
            raise Exception("yt-dlp no está instalado")

        if result.returncode != 0:
            raise Exception(f"yt-dlp falló: {result.stderr.strip()}")
        url = result.stdout.strip().split('\n')[0]
        if not url.startswith('http'):
            raise Exception(f"yt-dlp devolvió URL inválida: {url!r}")

        # Si yt-dlp cayó en el extractor genérico y devolvió la página embed,
        # no es una URL directa de video (archivo muerto o requiere login).
        if re.search(r'\.html?($|[?#])', url) or '/embed-' in url:
            raise Exception(f"Mp4upload: yt-dlp devolvió la página embed, no un video: {url}")

        self._validate_mp4upload_url(url)
        return url

    def _validate_mp4upload_url(self, url: str) -> None:
        """Valida que la URL directa del CDN de Mp4upload sirva video.

        Primero intenta un GET con Range (bytes=0-0) enviando Referer/Origin;
        si el CDN no responde a ese GET, cae en HEAD con las mismas cabeceras.
        """
        headers = {
            **self._headers,
            'Referer': _MP4UPLOAD_REFERER,
            'Origin':  _MP4UPLOAD_ORIGIN,
        }
        status, ct, cl = 0, '', 0
        try:
            with HttpPool.get_session().get(
                url, headers={**headers, 'Range': 'bytes=0-0'},
                stream=True, timeout=HTTP_TIMEOUT,
            ) as resp:
                status = resp.status_code
                ct     = resp.headers.get('content-type', '')
                cr     = resp.headers.get('content-range', '')
                if 'bytes' in cr:
                    total = cr.rsplit('/', 1)[-1]
                    if total.isdigit():
                        cl = int(total)
        except Exception as exc:
            logger.debug(f"Mp4upload: GET con rango no validó URL ({exc}), probando HEAD")

        if status >= 400 or not ct or 'html' in ct:
            try:
                head  = self.scraper.head(url, headers=headers, timeout=HTTP_TIMEOUT)
                status = head.status_code
                ct     = head.headers.get('content-type', '')
                cl     = int(head.headers.get('content-length', 0) or 0)
            except Exception as exc:
                logger.debug(f"Mp4upload: HEAD tampoco validó URL: {exc}")

        if status >= 400:
            raise Exception(f"Mp4upload: URL devolvió HTTP {status}")
        if 'html' in ct:
            raise Exception("Mp4upload: URL devolvió HTML en vez de video")
        if cl and cl < 10240:
            raise Exception(f"Mp4upload: archivo demasiado pequeño ({cl} bytes)")

    def _resolve_generic(self, slug: str) -> str:
        """Intenta obtener una URL directa de un servidor genérico (jkplayers)."""
        candidate = f"https://c1.jkplayers.com/d/{slug}/"
        rate_limiter.wait(candidate)
        resp = self.scraper.get(
            candidate, headers=self._headers, timeout=HTTP_TIMEOUT, allow_redirects=True
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

    def _resolve_mixdrop(self, encoded: str) -> tuple[str, str]:
        """Resuelve el MP4 directo de Mixdrop y el referer a usar en la descarga.

        El embed guarda la URL en `MDCore.wurl` dentro de un script ofuscado
        con el packer; se desofusca y se toma el valor de `wurl`.
        """
        embed_url = self._decode_remote(encoded)
        resp = self._get(embed_url)
        referer = resp.url
        decoded = _unpack_packed_js(resp.text)
        for block in decoded:
            m = re.search(r'MDCore\.wurl\s*=\s*"(//[^"]+)"', block)
            if m:
                return 'https:' + m.group(1), referer
        m = re.search(r'MDCore\.wurl\s*=\s*"(//[^"]+)"', resp.text)
        if m:
            return 'https:' + m.group(1), referer
        raise Exception("No se pudo extraer la URL directa de Mixdrop")

    def _resolve_wish_hls(self, encoded: str) -> tuple[str, str]:
        """Extrae la URL HLS (m3u8) de los embeds de la familia "wish" (Streamwish/Vidhide).

        La URL real se obtiene desofuscando el packer; se valida con un GET
        corto (muchos CDN responden 403 sin cabeceras adecuadas o por ASN).
        """
        embed_url = self._decode_remote(encoded)
        resp = self._get(embed_url)
        referer = resp.url
        decoded = _unpack_packed_js(resp.text)
        haystack = '\n'.join(decoded) + '\n' + resp.text
        # El packer parte las URLs largas con `.split('...')`; se descartan
        # esas piezas tomando solo URLs completas (sin comillas internas).
        m = re.search(r'https://[^"\'\\\s]+\.m3u8[^"\'\\\s]*', haystack)
        if not m:
            m = re.search(r'https://[^"\'\\\s]+\.txt[^"\'\\\s]*', haystack)
        if not m:
            raise Exception("No se pudo extraer URL HLS del embed")
        hls_url = m.group(0)
        check = self.scraper.get(
            hls_url,
            headers={**self._headers, 'Referer': referer},
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        if check.status_code >= 400:
            raise Exception(f"El CDN HLS rechazó la petición (HTTP {check.status_code})")
        return hls_url, referer

    def _download_hls(self, url: str, filepath: str,
                      referer: str | None = None, progress_cb=None) -> str:
        """Descarga un stream HLS (m3u8) a MP4 usando ffmpeg."""
        if not shutil.which('ffmpeg'):
            raise Exception("ffmpeg no está instalado (requerido para HLS)")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        headers = [f'User-Agent: {self.UA}']
        if referer:
            headers.append(f'Referer: {referer}')
        cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-headers', '\r\n'.join(headers) + '\r\n',
            '-rw_timeout', '30000000',
            '-i', url,
            '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
            filepath,
        ]
        if progress_cb:
            progress_cb(0, None, 'Descargando HLS')
        try:
            subprocess.run(cmd, check=True, timeout=_TIMEOUT_CURL)
        except subprocess.TimeoutExpired as exc:
            raise Exception("Timeout descargando HLS") from exc
        except subprocess.CalledProcessError as exc:
            raise Exception(f"ffmpeg no pudo descargar el HLS: {exc}") from exc
        if not os.path.exists(filepath) or os.path.getsize(filepath) < 10240:
            raise Exception("El archivo HLS descargado no es válido")
        return filepath

    # -----------------------------------------------------------------------
    # API pública (sync — llamada por BaseSource.search vía asyncio.to_thread)
    # -----------------------------------------------------------------------

    def search_sync(self, query: str) -> list[SearchResult]:
        """
        Busca animes por query.
        Ahora parsea título real, cover, estado y tipo desde .anime__item
        en lugar de generar datos a partir del slug.
        """
        encoded = _url_quote(query)
        url     = f"{self.BASE_URL}/buscar/{encoded}"
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.exception(f"Jkanime search error: {exc}")
            return []

        soup    = BeautifulSoup(html, 'html.parser')
        results = []

        for card in soup.select('.anime__item'):
            title_tag = card.select_one('.anime__item__text h5 a')
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get('href') or (card.select_one('a').get('href', '') if card.select_one('a') else '')

            # Imagen: primero data-setbg del pic-container, luego <img>
            pic = card.select_one('.anime__item__pic')
            image = (
                (pic.get('data-setbg') if pic else None)
                or (card.select_one('img') or {}).get('data-setbg')
                or (card.select_one('img') or {}).get('src')
            )

            # Extraer slug de la URL
            slug = None
            try:
                slug = href.strip('/').split('/')[-1] or None
            except Exception as exc:
                logger.debug('Jkanime: error extrayendo slug: %s', exc)

            # Estado y tipo desde los <li> de la card
            li_items = card.select('.anime__item__text ul li')
            type_    = li_items[-1].get_text(strip=True) if len(li_items) > 1 else None

            # Fallback de cover via CDN de jkdesa
            cover = image or (
                f"https://cdn.jkdesa.com/assets/images/animes/image/{slug}.jpg"
                if slug else None
            )

            if not slug:
                continue

            results.append(SearchResult(
                id=slug,
                title=title,
                cover=cover,
                type=type_,
            ))

        # Fallback si el HTML no trae .anime__item (ej. layout alternativo)
        if not results:
            logger.warning("Jkanime search: no se encontraron .anime__item, usando fallback regex")
            skip    = {'buscar', 'anime', 'ver', 'capitulo', 'tag', 'genero', 'categoria'}
            pattern = re.compile(r'href="https?://jkanime\.net/([a-z0-9][a-z0-9-]+)/"')
            slugs   = {m.group(1) for m in pattern.finditer(html) if m.group(1) not in skip}
            results = [
                SearchResult(
                    id=slug,
                    title=slug.replace('-', ' ').title(),
                    cover=f"https://cdn.jkdesa.com/assets/images/animes/image/{slug}.jpg",
                )
                for slug in slugs
            ]

        return results

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        """
        Devuelve detalles completos de una serie:
        title, titleAlt, cover, synopsis, status, type,
        total_episodes, start_date, genres, anime_id.
        """
        cover_fallback = f"https://cdn.jkdesa.com/assets/images/animes/image/{content_id}.jpg"
        try:
            html = self._get(f"{self.BASE_URL}/{content_id}/").text
        except Exception as exc:
            logger.exception(f"Jkanime get_details error para '{content_id}': {exc}")
            return SeriesDetails(title=content_id, cover=cover_fallback)

        soup = BeautifulSoup(html, 'html.parser')
        info = soup.select_one('.anime_info') or soup

        # Título principal
        title_elem = info.select_one('h3') or soup.select_one('h1.title, h1')
        title      = title_elem.get_text(strip=True) if title_elem else content_id

        # Sinopsis
        synopsis_elem = soup.select_one('p.scroll') or soup.select_one('.synopsis p')
        synopsis      = synopsis_elem.get_text(strip=True) if synopsis_elem else ''

        # Cover: intentar desde el HTML antes de caer en CDN
        cover_elem = info.select_one('img') or soup.select_one('.movpic img')
        cover = (
            (cover_elem.get('src') or cover_elem.get('data-setbg'))
            if cover_elem else None
        ) or cover_fallback

        # Campos de la lista de info (<li>)
        type_          = None
        total_episodes = None
        genres         = []

        for li in soup.select('li'):
            label_el = li.select_one('span') or li.select_one('div')
            if not label_el:
                continue
            label = label_el.get_text(strip=True).rstrip(':').strip().lower()
            full  = li.get_text(' ', strip=True)

            if label == 'tipo':
                type_ = full.replace('Tipo:', '').strip()

            elif label == 'episodios':
                raw = full.replace('Episodios:', '').strip()
                try:
                    total_episodes = int(raw)
                except ValueError:
                    pass

            elif label == 'generos':
                for a in li.select('a'):
                    name = a.get_text(strip=True)
                    if name:
                        genres.append({
                            'name': name,
                            'slug': name.lower().replace(' ', '-'),
                        })

        return SeriesDetails(
            title=title,
            cover=cover,
            synopsis=synopsis,
            type=type_,
            total_episodes=total_episodes,
            genres=genres,
        )

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        cache_key = f"jkanime:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return [Chapter(**c) if isinstance(c, dict) else c for c in cached]

        main_url = f"{self.BASE_URL}/{content_id}/"
        try:
            resp = self._get(main_url)
        except Exception as exc:
            logger.exception(f"Jkanime get_chapters error para '{content_id}': {exc}")
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
            logger.exception(f"Jkanime: no se pudo obtener serie_id para '{content_id}'")
            return []

        logger.debug(f"Jkanime: serie_id={serie_id} para '{content_id}'")

        token     = self._get_csrf_token(html)
        if not token:
            logger.warning("Jkanime: no se pudo obtener token CSRF, continuando sin él")
        post_data = {'_token': token} if token else {}

        # Intentar primero con GET (igual que el JS de referencia),
        # luego caer en POST si falla o no devuelve datos
        ajax_url  = f"{self.BASE_URL}/ajax/episodes/{serie_id}/1"
        data      = None

        try:
            get_resp = self._get(ajax_url, referer=main_url)
            data     = get_resp.json()
            if not data.get('total') and not data.get('data'):
                data = None
        except Exception as exc:
            logger.debug(f'Jkanime: GET AJAX falló para {content_id}: {exc}, usando POST')
            data = None

        if data is None:
            try:
                ajax_resp = self._post(ajax_url, data=post_data, referer=main_url)
                data      = ajax_resp.json()
            except Exception as exc:
                logger.exception(f"Jkanime: error en AJAX para '{content_id}': {exc}")
                return []

        total = data.get('total', 0)
        if total > 0:
            chapters = [Chapter(number=str(i), id=str(i)) for i in range(1, total + 1)]
            logger.info(f"Jkanime: {len(chapters)} capítulos para '{content_id}' (total directo)")
            search_cache.set(cache_key, [c.model_dump() for c in chapters])
            return chapters

        # Fallback: recorrer páginas
        chapters: list[Chapter] = []
        last_page = data.get('last_page', 1)

        for ep in data.get('data', []):
            num = ep.get('number')
            if num is not None:
                chapters.append(Chapter(number=str(num), id=str(num)))

        for page in range(2, last_page + 1):
            try:
                r         = self._post(
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
                    chapters.append(Chapter(number=str(num), id=str(num)))

        chapters.sort(key=lambda x: float(x.number))
        logger.info(f"Jkanime: {len(chapters)} capítulos para '{content_id}' (paginado)")
        search_cache.set(cache_key, [c.model_dump() for c in chapters])
        return chapters

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str,
                              chapter_number: str | None = None, progress_cb=None) -> str:
        html    = self._fetch_episode_html(content_id, chapter_id)
        soup    = BeautifulSoup(html, 'html.parser')

        # Resolver lista de servidores
        servers = self._parse_servers_from_table(soup)
        if not servers:
            servers = self._parse_servers_from_js(html)
        if not servers:
            # Descartar el HTML cacheado para que el reintento re-fetchee
            with self._cache_lock:
                self._episode_html_cache.pop(f"{content_id}/{chapter_id}", None)
            title = soup.title.get_text(strip=True)[:60] if soup.title else '?'
            logger.warning(
                f"Jkanime: sin servidores en {content_id}/{chapter_id} "
                f"(html_len={len(html)}, var_servers={'var servers' in html}, title={title!r})"
            )
            raise Exception("No se encontraron servidores de descarga")

        servers.sort(key=lambda s: (
            _SERVER_PRIORITY.index(s['server'])
            if s['server'] in _SERVER_PRIORITY else len(_SERVER_PRIORITY)
        ))

        # Ruta de destino común
        cap_num  = chapter_to_filename(chapter_id, padding=3) if chapter_id.replace('.', '', 1).isdigit() else chapter_id
        filename = f"{cap_num}.mp4"
        filepath = os.path.join(dest_folder, filename)
        os.makedirs(dest_folder, exist_ok=True)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.info(f"Jkanime: archivo ya existe, reutilizando: {filepath}")
            return filepath

        for server in servers:
            name   = server.get('server', '')
            remote = server.get('remote', '')
            slug   = server.get('slug', '')

            logger.info(f"Jkanime: probando servidor {name!r}")
            try:
                if name == 'Mediafire' and remote:
                    direct = self._resolve_mediafire(remote)
                    return self._download_stream(direct, filepath, progress_cb=progress_cb)

                elif name == 'Mp4upload' and remote:
                    # El token del CDN expira rápido: re-resolver con URL fresca
                    # antes de rendirse (curl también valida magic bytes MP4).
                    for attempt in range(2):
                        try:
                            direct = self._resolve_mp4upload(remote)
                            return self._download_curl(
                                direct, filepath,
                                referer=_MP4UPLOAD_REFERER,
                                origin=_MP4UPLOAD_ORIGIN,
                                progress_cb=progress_cb,
                            )
                        except Exception as exc:
                            if attempt == 1:
                                raise
                            logger.warning(
                                f"Mp4upload: intento {attempt + 1} falló ({exc}), "
                                f"reintentando con token fresco"
                            )
                            if os.path.exists(filepath):
                                os.remove(filepath)

                elif name == 'Mixdrop' and remote:
                    direct, referer = self._resolve_mixdrop(remote)
                    origin = f"{urlsplit(referer).scheme}://{urlsplit(referer).netloc}"
                    return self._download_curl(direct, filepath,
                                               referer=referer, origin=origin,
                                               progress_cb=progress_cb)

                elif name in ('Streamwish', 'Vidhide') and remote:
                    hls_url, referer = self._resolve_wish_hls(remote)
                    return self._download_hls(hls_url, filepath, referer=referer,
                                              progress_cb=progress_cb)

                elif slug:
                    direct = self._resolve_generic(slug)
                    return self._download_stream(direct, filepath,
                                                 referer=self.BASE_URL,
                                                 progress_cb=progress_cb)

            except Exception as exc:
                logger.warning(f"Jkanime: servidor {name!r} falló: {exc}")
                # Limpiar archivo parcial (vacío o corrupto) antes del siguiente servidor
                if os.path.exists(filepath):
                    os.remove(filepath)
                continue

        raise Exception(f"No se pudo descargar el capítulo {chapter_id} desde ningún servidor")

    @property
    def supports_streaming(self) -> bool:
        return True

    def get_stream_url_sync(self, content_id: str, chapter_id: str) -> str | None:
        """
        Devuelve la mejor URL de streaming disponible para el episodio.

        Estrategia (en orden):
          1. Iframes embebidos desde video[N] en el HTML (JKPlayer nativo)
          2. Servidores con remote base64 que sean conocidos como streamables
          3. Primer servidor disponible como último recurso

        Devuelve None si no se encuentra ninguna opción.
        """
        try:
            html = self._fetch_episode_html(content_id, chapter_id)
        except Exception as exc:
            logger.exception(f"Jkanime get_stream_url error: {exc}")
            return None

        # 1. Iframes nativos del JKPlayer (video[0] = "<iframe src='...'/>")
        iframe_urls = self._parse_iframe_urls(html)
        if iframe_urls:
            logger.info(f"Jkanime stream: usando iframe JKPlayer para {content_id}/{chapter_id}")
            return iframe_urls[0]

        # 2. Servidores con remote base64 — priorizar los streamables
        servers = self._parse_servers_from_js(html)
        if not servers:
            servers = self._parse_servers_from_table(BeautifulSoup(html, 'html.parser'))

        # Ordenar: primero los streamables, luego el resto
        def _stream_priority(s: dict) -> int:
            token = s.get('server', '').lower().replace(' ', '')
            return 0 if any(k in token for k in _STREAM_SERVERS) else 1

        servers_sorted = sorted(servers, key=_stream_priority)

        for server in servers_sorted:
            remote = server.get('remote', '')
            name   = server.get('server', '')
            if not remote:
                continue
            try:
                url = self._decode_remote(remote)
                if url.startswith('http'):
                    logger.info(f"Jkanime stream: usando servidor {name!r} para {content_id}/{chapter_id}")
                    return url
            except Exception as exc:
                logger.debug(f"Jkanime stream: fallo decodificando remote de {name!r}: {exc}")
                continue

        logger.warning(f"Jkanime get_stream_url: sin opciones de stream para {content_id}/{chapter_id}")
        return None

    def get_episode_links(self, content_id: str, chapter_id: str) -> EpisodeLinks:
        """
        Devuelve todos los links de stream y descarga del episodio,
        separados por variante (SUB / DUB).

        Estructura de retorno:
        {
            'stream':   { 'SUB': [...], 'DUB': [...] },
            'download': { 'SUB': [...], 'DUB': [...] },
        }
        Cada entry: { 'server': str, 'url': str }
        """
        try:
            html = self._fetch_episode_html(content_id, chapter_id)
        except Exception as exc:
            logger.exception(f"Jkanime get_episode_links error: {exc}")
            return EpisodeLinks()

        soup    = BeautifulSoup(html, 'html.parser')
        servers = self._parse_servers_from_js(html)
        if not servers:
            servers = self._parse_servers_from_table(soup)

        # Extraer var remote del HTML para construir URLs de descarga
        remote_base_match = re.search(r"var\s+remote\s*=\s*['\"]([^'\"]+)['\"]", html)
        remote_base       = remote_base_match.group(1) if remote_base_match else None

        seen_stream   = set()
        seen_download = set()
        stream_links   = {'SUB': [], 'DUB': []}
        download_links = {'SUB': [], 'DUB': []}

        for server in servers:
            name    = server.get('server', '')
            remote  = server.get('remote', '')
            slug    = server.get('slug', '')
            variant = server.get('variant', 'SUB')

            # Stream: decodificar remote base64
            if remote:
                try:
                    stream_url = self._decode_remote(remote)
                    if stream_url.startswith('http') and stream_url not in seen_stream:
                        seen_stream.add(stream_url)
                        stream_links[variant].append(EpisodeLink(server=name, url=stream_url))
                except Exception as exc:
                    logger.debug(f'Jkanime: error decodificando remote para {name}: {exc}')

            # Download: construir URL desde remote_base + slug
            if remote_base and slug:
                dl_url = f"{remote_base.rstrip('/')}/d/{slug}/"
                if dl_url not in seen_download:
                    seen_download.add(dl_url)
                    download_links[variant].append(EpisodeLink(server=name, url=dl_url))

        # Iframes JKPlayer siempre como SUB en stream
        for url in self._parse_iframe_urls(html):
            if url not in seen_stream:
                seen_stream.add(url)
                stream_links['SUB'].append(EpisodeLink(server='JKPlayer', url=url))

        return EpisodeLinks(stream=stream_links, download=download_links)
