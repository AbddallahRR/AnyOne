#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import logging
import os
import re
import subprocess
from urllib.parse import quote as _url_quote

from bs4 import BeautifulSoup

from core.disk_cache import search_cache
from core.http_pool import HttpPool
from core.models import Chapter, EpisodeLink, EpisodeLinks, SearchResult, SeriesDetails
from core.throttle import rate_limiter

from . import BaseSource

logger = logging.getLogger(__name__)

# Prioridad de servidores (índice menor = mayor prioridad)
_SERVER_PRIORITY = [
    'Mediafire', 'Mp4upload', 'Mega',
    'Streamwish', 'VOE', 'Vidhide', 'Mixdrop', 'Streamtape', 'Doodstream',
]

# Servidores que soportan streaming directo (iframe embebible)
_STREAM_SERVERS = {'streamwish', 'voe', 'vidhide', 'mixdrop', 'streamtape', 'doodstream'}

# Timeouts
_TIMEOUT_HTTP = 30
_TIMEOUT_CURL = 1800   # 30 min por intento de descarga


class JkanimeSource(BaseSource):
    type = 'anime'
    label = 'JKanime'
    BASE_URL = "https://jkanime.net"
    UA       = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    def __init__(self):
        self.scraper = HttpPool.get_scraper()

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, referer: str | None = None, **kwargs):
        rate_limiter.wait(url)
        headers = {**self._headers}
        if referer:
            headers['Referer'] = referer
        kwargs.setdefault('timeout', _TIMEOUT_HTTP)
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, data=None, referer: str | None = None):
        rate_limiter.wait(url)
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

    @staticmethod
    def _normalize_variant(lang: str | None) -> str:
        """Normaliza el campo lang a 'SUB' o 'DUB'."""
        token = (lang or '').lower().replace(' ', '')
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
                except Exception:
                    pass

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
                         referer: str | None = None) -> str:
        """
        Descarga un MP4 via requests con streaming.
        Elimina el archivo si falla a mitad.
        """
        headers = {**self._headers}
        if referer:
            headers['Referer'] = referer

        with HttpPool.get_session().get(url, headers=headers, stream=True, timeout=60) as r:
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
        rate_limiter.wait(candidate)
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
            logger.error(f"Jkanime search error: {exc}")
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
            except Exception:
                pass

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
            logger.error(f"Jkanime get_details error para '{content_id}': {exc}")
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
        except Exception:
            data = None

        if data is None:
            try:
                ajax_resp = self._post(ajax_url, data=post_data, referer=main_url)
                data      = ajax_resp.json()
            except Exception as exc:
                logger.error(f"Jkanime: error en AJAX para '{content_id}': {exc}")
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
                try:
                    if float(num) != int(float(num)):
                        logger.debug(f"Jkanime: ignorando capítulo decimal {num!r} en '{content_id}'")
                        continue
                except (ValueError, TypeError):
                    pass
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
                    try:
                        if float(num) != int(float(num)):
                            logger.debug(f"Jkanime: ignorando capítulo decimal {num!r} en '{content_id}'")
                            continue
                    except (ValueError, TypeError):
                        pass
                    chapters.append(Chapter(number=str(num), id=str(num)))

        chapters.sort(key=lambda x: int(x.number))
        logger.info(f"Jkanime: {len(chapters)} capítulos para '{content_id}' (paginado)")
        search_cache.set(cache_key, [c.model_dump() for c in chapters])
        return chapters

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str, chapter_number: str | None = None) -> str:
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
            name   = server.get('server', '')
            remote = server.get('remote', '')
            slug   = server.get('slug', '')

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

    def get_stream_url_sync(self, content_id: str, chapter_id: str) -> str | None:
        """
        Devuelve la mejor URL de streaming disponible para el episodio.

        Estrategia (en orden):
          1. Iframes embebidos desde video[N] en el HTML (JKPlayer nativo)
          2. Servidores con remote base64 que sean conocidos como streamables
          3. Primer servidor disponible como último recurso

        Devuelve None si no se encuentra ninguna opción.
        """
        cap_url = f"{self.BASE_URL}/{content_id}/{chapter_id}/"
        try:
            html = self._get(cap_url).text
        except Exception as exc:
            logger.error(f"Jkanime get_stream_url error: {exc}")
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
        cap_url = f"{self.BASE_URL}/{content_id}/{chapter_id}/"
        try:
            html = self._get(cap_url).text
        except Exception as exc:
            logger.error(f"Jkanime get_episode_links error: {exc}")
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
                except Exception:
                    pass

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
