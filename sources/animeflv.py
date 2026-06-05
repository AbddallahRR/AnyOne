#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import re

import requests
import cloudscraper
from bs4 import BeautifulSoup

from . import BaseSource
from core.disk_cache import search_cache
from core.models import Chapter, EpisodeLink, EpisodeLinks, SearchResult, SeriesDetails
from core.throttle import rate_limiter

logger = logging.getLogger(__name__)

# Prioridad de servidores (índice menor = mayor prioridad)
_SERVER_PRIORITY = [
    'Mega', 'Mediafire', 'Mp4upload',
    'Streamwish', 'VOE', 'Vidhide', 'Mixdrop', 'Streamtape', 'Doodstream',
]

# Servidores que soportan streaming directo (iframe embebible)
_STREAM_SERVERS = {'streamwish', 'voe', 'vidhide', 'mixdrop', 'streamtape', 'doodstream', 'yourupload'}

# Timeouts
_TIMEOUT_HTTP = 30

# Dominio por defecto (puede cambiar; se intenta detectar automáticamente)
_DEFAULT_DOMAIN = "www3.animeflv.net"


class AnimeflvSource(BaseSource):
    UA = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"

    def __init__(self):
        self.scraper  = cloudscraper.create_scraper()
        self._domain  = _DEFAULT_DOMAIN

    # -----------------------------------------------------------------------
    # HTTP helpers
    # -----------------------------------------------------------------------

    @property
    def _headers(self) -> dict:
        return {
            'User-Agent':      self.UA,
            'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        }

    @property
    def BASE_URL(self) -> str:
        return f"https://{self._domain}"

    def _get(self, url: str, referer: str | None = None, **kwargs):
        rate_limiter.wait(url)
        headers = {**self._headers}
        if referer:
            headers['Referer'] = referer
        kwargs.setdefault('timeout', _TIMEOUT_HTTP)
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _resolve_url(self, path: str) -> str:
        """Convierte un path relativo en URL absoluta usando el dominio activo."""
        if path.startswith('http'):
            return path
        return f"{self.BASE_URL}/{path.lstrip('/')}"

    # -----------------------------------------------------------------------
    # Parsing helpers — variables JS
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_var_literal(html: str, var_name: str) -> str | None:
        """
        Extrae el literal (array u objeto) asignado a una variable JS.
        Equivalente al extractVarLiteral del JS de referencia.
        Maneja strings con comillas simples/dobles/backtick y escapes.
        """
        marker = f'var {var_name}'
        start  = html.find(marker)
        if start == -1:
            return None

        eq = html.find('=', start)
        if eq == -1:
            return None

        slice_ = html[eq + 1:]
        bracket_m = re.search(r'[\[{]', slice_)
        if not bracket_m:
            return None

        open_idx  = bracket_m.start()
        open_char = slice_[open_idx]
        close_char = '}' if open_char == '{' else ']'

        depth       = 0
        active_quote = ''
        escaped     = False

        for i, ch in enumerate(slice_[open_idx:], start=open_idx):
            if active_quote:
                if escaped:
                    escaped = False
                    continue
                if ch == '\\':
                    escaped = True
                    continue
                if ch == active_quote:
                    active_quote = ''
                continue

            if ch in ('"', "'", '`'):
                active_quote = ch
                continue

            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return slice_[open_idx: i + 1]

        return None

    @staticmethod
    def _safe_evaluate(expression: str):
        """
        Evalúa un literal JSON/JS de forma segura.
        Normaliza comillas simples y trailing commas antes de parsear.
        """
        try:
            # Primero intento directo con json.loads
            return json.loads(expression)
        except Exception:
            pass

        try:
            # Normalizar: comillas simples → dobles, trailing commas
            cleaned = expression.replace("'", '"')
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            return json.loads(cleaned)
        except Exception:
            return None

    @staticmethod
    def _try_decode_base64(value: str) -> str | None:
        """
        Intenta decodificar un valor base64 si parece una URL codificada.
        Equivalente al tryDecodeBase64 del JS de referencia.
        """
        import base64
        if not value or not isinstance(value, str):
            return None
        if not re.match(r'^[A-Za-z0-9+/=]+$', value) or len(value) < 10:
            return None
        try:
            decoded = base64.b64decode(value).decode('utf-8', errors='ignore')
            if decoded.startswith(('http://', 'https://')):
                return decoded
        except Exception:
            pass
        return None

    @staticmethod
    def _decode_url_escapes(value: str) -> str:
        """Decodifica escapes unicode y HTML comunes en URLs."""
        if not value:
            return value
        return (
            value
            .replace(r'\u0026', '&')
            .replace(r'\u003A', ':')
            .replace(r'\u002F', '/')
            .replace('&amp;', '&')
        )

    # -----------------------------------------------------------------------
    # Parsing helpers — contenido HTML
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalize_variant(value: str | None) -> str:
        """Normaliza el key de variante a 'SUB' o 'DUB'."""
        token = (value or '').lower().replace(' ', '')
        if any(k in token for k in ('sub', 'jap', 'jp')):
            return 'SUB'
        # AnimeFLV usa 'latino' / 'esp' / 'cast' para doblaje
        if any(k in token for k in ('dub', 'lat', 'esp', 'cast')):
            return 'DUB'
        return 'SUB'

    def _parse_search_results(self, html: str) -> list[SearchResult]:
        soup    = BeautifulSoup(html, 'html.parser')
        results = []

        cards = soup.select('article.Anime, .ListAnimes li article')
        for card in cards:
            link_tag = card.select_one("a[href^='/anime/']") or card.select_one('a')
            title_el = card.select_one('h3.Title') or card.select_one('img')
            if not link_tag or not title_el:
                continue

            href  = link_tag.get('href', '')
            title = (
                title_el.get_text(strip=True)
                if title_el.name != 'img'
                else title_el.get('alt', '')
            )
            if not href or not title:
                continue

            img   = card.select_one('img')
            image = (img.get('src') or img.get('data-src')) if img else None
            slug  = href.rstrip('/').split('/')[-1] or None
            type_ = card.select_one('.Type')

            results.append(SearchResult(
                id=slug,
                title=title,
                cover=self._resolve_url(image) if image else None,
                type=type_.get_text(strip=True) if type_ else None,
            ))

        return results

    def _parse_anime_info(self, html: str) -> SeriesDetails:
        soup = BeautifulSoup(html, 'html.parser')

        title_el = soup.select_one('h1')
        title    = title_el.get_text(strip=True) if title_el else None

        desc_el  = soup.select_one('.Description') or soup.select_one('.Anime-Description')
        synopsis = desc_el.get_text(strip=True) if desc_el else ''

        cover_el = (
            soup.select_one('.AnimeCover img')
            or soup.select_one('.cover img')
            or soup.select_one('.Anime img')
        )
        image = None
        if cover_el:
            image = cover_el.get('src') or cover_el.get('data-src')

        genres = []
        for a in soup.select('.Nvgnrs a, .ListAnmRel a'):
            name = a.get_text(strip=True)
            if name:
                genres.append({
                    'name': name,
                    'slug': name.lower().replace(' ', '-'),
                })

        type_el = soup.select_one('.Type')
        type_   = type_el.get_text(strip=True) if type_el else None

        return SeriesDetails(
            title=title or '',
            synopsis=synopsis,
            image=image,
            genres=genres,
            type=type_,
            cover=self._resolve_url(image) if image else None,
        )

    def _parse_episodes_from_html(self, html: str, slug: str) -> list[dict]:
        """
        Extrae episodios desde links <a href='/ver/...'> en el HTML.
        Equivalente al parseEpisodesFromHtml del JS de referencia.
        """
        soup     = BeautifulSoup(html, 'html.parser')
        episodes = []
        seen     = set()

        for a in soup.select("a[href^='/ver/'], a[href*='/ver/']"):
            href = a.get('href', '')
            if not href:
                continue
            url = self._resolve_url(href)
            if url in seen:
                continue
            num = self._episode_number_from_url(url)
            if not num:
                continue
            seen.add(url)
            episodes.append({
                'number': num,
                'id':     str(num),
                'url':    url,
            })

        return episodes

    def _parse_episodes_from_script(self, html: str, slug: str) -> list[dict]:
        """
        Extrae episodios desde var episodes = [...] en el HTML.
        Equivalente al parseEpisodeListFromScript del JS de referencia.
        Cada entrada JS es [number, id].
        """
        literal = self._extract_var_literal(html, 'episodes')
        if not literal:
            return []

        data = self._safe_evaluate(literal)
        if not isinstance(data, list):
            return []

        episodes = []
        for entry in data:
            if not isinstance(entry, list) or not entry:
                continue
            try:
                number = int(entry[0])
            except (ValueError, TypeError):
                continue
            ep_id  = entry[1] if len(entry) > 1 else None
            ep_url = f"{self.BASE_URL}/ver/{slug}-{number}"
            episodes.append({
                'number': number,
                'id':     str(ep_id) if ep_id is not None else str(number),
                'url':    ep_url,
            })

        return episodes

    def _parse_video_sources(self, html: str) -> dict | None:
        """
        Extrae y decodifica var videos = {...} del HTML del episodio.
        Equivalente al parseVideoSources del JS de referencia.
        Decodifica base64 y escapes unicode en los campos de URL.
        """
        literal = self._extract_var_literal(html, 'videos')
        if not literal:
            return None

        data = self._safe_evaluate(literal)
        if not isinstance(data, dict):
            return None

        url_fields = ('code', 'url', 'embed', 'file')

        for entries in data.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for field in url_fields:
                    val = entry.get(field)
                    if not isinstance(val, str):
                        continue
                    decoded = self._try_decode_base64(val)
                    if decoded:
                        entry[field] = decoded
                    else:
                        entry[field] = self._decode_url_escapes(val)

        return data

    def _parse_download_rows(self, html: str) -> list[dict]:
        """
        Extrae filas de la tabla de descargas del HTML del episodio.
        Equivalente al parseDownloadRows del JS de referencia.
        """
        soup = BeautifulSoup(html, 'html.parser')
        rows = []

        for tr in soup.select('table tbody tr'):
            cells   = tr.find_all('td')
            if len(cells) < 2:
                continue
            server  = cells[0].get_text(strip=True) or None
            format_ = cells[1].get_text(strip=True) if len(cells) > 1 else None
            variant = cells[2].get_text(strip=True) if len(cells) > 2 else None
            a_tag   = tr.find('a')
            url     = a_tag.get('href') if a_tag else None
            if not url:
                continue
            rows.append({
                'server':  server,
                'format':  format_,
                'variant': variant,
                'url':     self._resolve_url(url),
            })

        return rows

    # -----------------------------------------------------------------------
    # Utilidades
    # -----------------------------------------------------------------------

    @staticmethod
    def _episode_number_from_url(url: str) -> int | None:
        """Extrae el número de episodio del último segmento de la URL."""
        try:
            segment = url.rstrip('/').split('/')[-1]
            m = re.search(r'(\d+)\D*$', segment)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return None

    @staticmethod
    def _dedup_links(links: list[dict], seen: set) -> list[dict]:
        result = []
        for link in links:
            url = link.get('url')
            if url and url not in seen:
                seen.add(url)
                result.append(link)
        return result

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    def search(self, query: str) -> list[SearchResult]:
        encoded = requests.utils.quote(query)
        url     = f"{self.BASE_URL}/browse?q={encoded}"
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.error(f"Animeflv search error: {exc}")
            return []

        results = self._parse_search_results(html)

        if not results:
            logger.warning("Animeflv search: no se encontraron resultados con selectores principales")

        return results

    def get_details(self, content_id: str) -> SeriesDetails:
        url = f"{self.BASE_URL}/anime/{content_id}"
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.error(f"Animeflv get_details error para '{content_id}': {exc}")
            return SeriesDetails(title=content_id)

        info     = self._parse_anime_info(html)
        episodes = self._parse_episodes_from_html(html, content_id)
        if not episodes:
            episodes = self._parse_episodes_from_script(html, content_id)

        info.total_episodes = len(episodes) if episodes else None
        info.title = info.title or content_id
        return info

    def get_chapters(self, content_id: str) -> list[Chapter]:
        cache_key = f"animeflv:chapters:{content_id}"
        cached    = search_cache.get(cache_key)
        if cached is not None:
            return [Chapter(**c) if isinstance(c, dict) else c for c in cached]

        url = f"{self.BASE_URL}/anime/{content_id}"
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.error(f"Animeflv get_chapters error para '{content_id}': {exc}")
            return []

        episodes = self._parse_episodes_from_html(html, content_id)

        if not episodes:
            logger.debug(f"Animeflv: sin links /ver/ en HTML para '{content_id}', usando script")
            episodes = self._parse_episodes_from_script(html, content_id)

        if not episodes:
            logger.error(f"Animeflv: no se encontraron episodios para '{content_id}'")
            return []

        chapters = [
            Chapter(number=str(ep['number']), id=str(ep['id']))
            for ep in sorted(episodes, key=lambda e: e['number'])
        ]

        logger.info(f"Animeflv: {len(chapters)} capítulos para '{content_id}'")
        search_cache.set(cache_key, [c.model_dump() for c in chapters])
        return chapters

    def download_chapter(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        """
        AnimeFLV no ofrece descarga directa confiable; los links van a hosts externos.
        Intenta con yt-dlp sobre los sources embebidos.
        Lanza Exception si no puede descargar.
        """
        import os
        import subprocess

        cap_url  = f"{self.BASE_URL}/ver/{content_id}-{chapter_id}"
        try:
            html = self._get(cap_url).text
        except Exception as exc:
            raise Exception(f"No se pudo obtener el episodio: {exc}")

        stream_url = self._best_stream_url(html)
        if not stream_url:
            raise Exception("No se encontró URL de stream para el episodio")

        cap_num  = int(float(chapter_id)) if str(chapter_id).replace('.', '', 1).isdigit() else 0
        filename = f"{content_id}_{cap_num:03d}.mp4"
        filepath = os.path.join(dest_folder, filename)
        os.makedirs(dest_folder, exist_ok=True)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            logger.info(f"Animeflv: archivo ya existe, reutilizando: {filepath}")
            return filepath

        logger.info(f"Animeflv: descargando con yt-dlp desde {stream_url}")
        try:
            subprocess.run(
                [
                    'yt-dlp', '-o', filepath,
                    '--no-warnings', '--quiet',
                    stream_url,
                ],
                check=True,
                timeout=1800,
            )
        except FileNotFoundError:
            raise Exception("yt-dlp no está instalado")
        except subprocess.CalledProcessError as exc:
            raise Exception(f"yt-dlp falló: {exc}")

        return filepath

    def get_stream_url(self, content_id: str, chapter_id: str) -> str | None:
        """
        Devuelve la mejor URL de streaming disponible para el episodio.

        Estrategia (en orden):
          1. Servidores streamables conocidos de var videos (SUB primero)
          2. Cualquier entry con URL válida en var videos
          3. None si no hay nada utilizable
        """
        cap_url = f"{self.BASE_URL}/ver/{content_id}-{chapter_id}"
        try:
            html = self._get(cap_url).text
        except Exception as exc:
            logger.error(f"Animeflv get_stream_url error: {exc}")
            return None

        return self._best_stream_url(html)

    def get_episode_links(self, content_id: str, chapter_id: str) -> EpisodeLinks:
        cap_url = f"{self.BASE_URL}/ver/{content_id}-{chapter_id}"
        try:
            html = self._get(cap_url).text
        except Exception as exc:
            logger.error(f"Animeflv get_episode_links error: {exc}")
            return EpisodeLinks()

        stream_links   = {'SUB': [], 'DUB': []}
        download_links = {'SUB': [], 'DUB': []}
        seen_stream    = set()
        seen_download  = set()

        video_sources = self._parse_video_sources(html)
        if video_sources:
            for key, entries in video_sources.items():
                if not isinstance(entries, list):
                    continue
                variant = self._normalize_variant(key)
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    url = (
                        entry.get('code')
                        or entry.get('url')
                        or entry.get('embed')
                        or entry.get('file')
                    )
                    server = entry.get('title') or entry.get('server') or 'Unknown'
                    if url and url not in seen_stream:
                        seen_stream.add(url)
                        stream_links[variant].append(EpisodeLink(server=server, url=url))

        for row in self._parse_download_rows(html):
            variant = self._normalize_variant(row.get('variant'))
            url     = row.get('url')
            server  = row.get('server') or 'Download'
            if url and url not in seen_download:
                seen_download.add(url)
                download_links[variant].append(EpisodeLink(
                    server=server,
                    url=url,
                    format=row.get('format'),
                ))

        return EpisodeLinks(stream=stream_links, download=download_links)

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _best_stream_url(self, html: str) -> str | None:
        """
        Elige la mejor URL de streaming desde el HTML de un episodio.
        Prioriza servidores en _STREAM_SERVERS, luego cualquier URL válida.
        SUB tiene precedencia sobre DUB.
        """
        video_sources = self._parse_video_sources(html)
        if not video_sources:
            return None

        url_fields = ('code', 'url', 'embed', 'file')

        # Agrupar por variante para priorizar SUB
        candidates: list[tuple[int, str, str]] = []  # (priority, server_token, url)

        for key, entries in video_sources.items():
            if not isinstance(entries, list):
                continue
            variant      = self._normalize_variant(key)
            variant_bias = 0 if variant == 'SUB' else 100

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                url = next((entry[f] for f in url_fields if entry.get(f)), None)
                if not url or not url.startswith('http'):
                    continue
                server_name  = (entry.get('title') or entry.get('server') or '').lower()
                server_token = re.sub(r'[^a-z0-9]', '', server_name)

                stream_list = list(_STREAM_SERVERS)
                if server_token in stream_list:
                    # Menor índice = mayor prioridad dentro de los streamables
                    priority = variant_bias + stream_list.index(server_token)
                else:
                    priority = variant_bias + len(stream_list)

                candidates.append((priority, server_token, url))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][2]