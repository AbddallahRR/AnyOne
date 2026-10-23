#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import re
import subprocess
from collections import OrderedDict
from typing import Any
from urllib.parse import quote_plus, urlsplit

from bs4 import BeautifulSoup

from core.http_pool import HTTP_TIMEOUT, HttpPool
from core.models import Chapter, EpisodeLink, EpisodeLinks, SearchResult, SeriesDetails, chapter_to_filename

from . import BaseSource
from .common import HttpClientMixin
from .jkanime import _MP4UPLOAD_ORIGIN, _MP4UPLOAD_REFERER, JkanimeSource

logger = logging.getLogger(__name__)

_STREAM_SERVERS = {'hls', 'voe', 'byse', 'upnshare', 'streamwish', 'vidhide', 'mixdrop', 'streamtape', 'doodstream', 'zilla', 'player'}


class AnimeAV1Source(HttpClientMixin, BaseSource):
    type = 'anime'
    label = 'AnimeAV1'
    BASE_URL = "https://animeav1.com"

    _run_curl_with_progress = JkanimeSource._run_curl_with_progress

    _episode_html_cache: OrderedDict[str, str] = OrderedDict()
    _serie_page_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def __init__(self):
        super().__init__()
        self.scraper = HttpPool.get_scraper()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_balanced(text: str, start: int) -> str | None:
        """Devuelve el objeto {...} balanceado que empieza en `start`."""
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    @staticmethod
    def _extract_sveltekit_data(html: str) -> dict[str, Any] | None:
        """Extrae el objeto data embebido por SvelteKit.

        El payload usa literales JS (claves sin comillas), así que se
        convierten a JSON antes de parsear.
        """
        m = re.search(r'kit\.start\([^,]+,[^,]+,\s*(\{)', html)
        if not m:
            return None
        raw = AnimeAV1Source._extract_balanced(html, m.start(1))
        if not raw:
            return None
        try:
            conv = re.sub(r'([{,\[])\s*([A-Za-z_$][\w$]*)\s*:', r'\1"\2":', raw)
            conv = re.sub(r'(?<=[:,])\s*void 0\b', ' null', conv)
            payload = json.loads(conv)
        except Exception:
            return None

        data = payload.get('data')
        if isinstance(data, list):
            # Suele estar en el último elemento con type:"data"
            for item in reversed(data):
                if isinstance(item, dict) and item.get('type') == 'data' and isinstance(item.get('data'), dict):
                    return item['data']
            # Fallback: primer dict con media/episode/embeds
            for item in data:
                if isinstance(item, dict):
                    inner = item.get('data') if isinstance(item.get('data'), dict) else item
                    if isinstance(inner, dict) and (inner.get('media') or inner.get('embeds') or inner.get('episodes')):
                        return inner
        elif isinstance(data, dict):
            return data
        return None

    def _fetch_serie_page(self, slug: str) -> str:
        url = f"{self.BASE_URL}/media/{slug}"
        return self._get(url).text

    def _fetch_episode_page(self, slug: str, episode: str) -> str:
        url = f"{self.BASE_URL}/media/{slug}/{episode}"
        return self._get(url).text

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    def search_sync(self, query: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen = set()
        ql = query.lower().strip()
        if not ql:
            return results

        # 1) Intentar búsqueda directa con formato que indica el sitio: /catalogo?search=...
        try:
            url = f"{self.BASE_URL}/catalogo?search={quote_plus(query)}"
            html = self._get(url).text
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.select('a[href^="/media/"]'):
                href = a.get('href') or ''
                if not href:
                    continue
                parts = href.strip('/').split('/')
                if len(parts) != 2 or parts[0] != 'media':
                    continue
                slug = parts[1]
                if not slug or slug in seen or re.match(r'^\d+$', slug):
                    continue

                card = a
                title = None
                for sel in ['h3', 'h2', '.title', '[class*="title"]']:
                    t = card.select_one(sel)
                    if t and t.get_text(strip=True):
                        title = t.get_text(strip=True)
                        break
                if not title:
                    img = card.find('img')
                    if img and img.get('alt'):
                        title = img.get('alt').strip()
                if not title:
                    title = slug.replace('-', ' ').title()

                img = card.find('img')
                cover = None
                if img:
                    cover = img.get('src') or img.get('data-src') or img.get('data-setbg')
                if not cover:
                    # Buscar en padres (estructura con hover/card)
                    parent = card.parent
                    for _ in range(5):
                        if not parent:
                            break
                        for im in parent.find_all('img'):
                            src = im.get('src') or im.get('data-src') or im.get('data-setbg')
                            if src and 'covers' in src or src and src.startswith('http'):
                                cover = src
                                break
                        if cover:
                            break
                        parent = parent.parent
                if cover and cover.startswith('//'):
                    cover = 'https:' + cover
                if cover and cover.startswith('/'):
                    cover = self.BASE_URL + cover

                seen.add(slug)
                results.append(SearchResult(id=slug, title=title, cover=cover))
            if results:
                return results
        except Exception as exc:
            logger.debug(f"AnimeAV1: búsqueda por /catalogo?search falló: {exc}")

        # 2) Fallback: scrapear catálogo completo/home
        try:
            html = self._get(self.BASE_URL + "/catalogo").text
        except Exception:
            try:
                html = self._get(self.BASE_URL + "/").text
            except Exception as exc:
                logger.exception(f"AnimeAV1 search error: {exc}")
                return []

        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.select('a[href^="/media/"]'):
            href = a.get('href') or ''
            if not href:
                continue
            parts = href.strip('/').split('/')
            if len(parts) != 2 or parts[0] != 'media':
                continue
            slug = parts[1]
            if not slug or slug in seen or re.match(r'^\d+$', slug):
                continue

            card = a
            title = None
            for sel in ['h3', 'h2', '.title', '[class*="title"]']:
                t = card.select_one(sel)
                if t and t.get_text(strip=True):
                    title = t.get_text(strip=True)
                    break
            if not title:
                img = card.find('img')
                if img and img.get('alt'):
                    title = img.get('alt').strip()
            if not title:
                title = slug.replace('-', ' ').title()

            if ql not in title.lower() and ql not in slug.lower():
                continue

            img = card.find('img')
            cover = None
            if img:
                cover = img.get('src') or img.get('data-src') or img.get('data-setbg')
            if not cover:
                parent = card.parent
                for _ in range(5):
                    if not parent:
                        break
                    for im in parent.find_all('img'):
                        src = im.get('src') or im.get('data-src') or im.get('data-setbg')
                        if src:
                            cover = src
                            break
                    if cover:
                        break
                    parent = parent.parent
            if cover and cover.startswith('//'):
                cover = 'https:' + cover
            if cover and cover.startswith('/'):
                cover = self.BASE_URL + cover

            seen.add(slug)
            results.append(SearchResult(id=slug, title=title, cover=cover))

        return results

    # -----------------------------------------------------------------------
    # Details
    # -----------------------------------------------------------------------

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        slug = content_id.strip('/')
        try:
            html = self._fetch_serie_page(slug)
        except Exception as exc:
            logger.exception(f"AnimeAV1 get_details error: {exc}")
            return SeriesDetails(title=slug)

        data = self._extract_sveltekit_data(html)
        media = None
        if data:
            media = data.get('media') or (data.get('data') or {}).get('media')

        if media and isinstance(media, dict):
            title = media.get('title') or slug.replace('-', ' ').title()
            cover = media.get('poster') or media.get('cover')
            if not cover and media.get('id'):
                # El payload trae poster:null; la portada vive en el CDN por id
                cover = f"https://cdn.animeav1.com/covers/{media['id']}.jpg"
            if cover and isinstance(cover, str) and cover.startswith('//'):
                cover = 'https:' + cover
            synopsis = media.get('synopsis') or ''
            genres = []
            for g in media.get('genres') or []:
                if isinstance(g, dict) and g.get('name'):
                    genres.append({'name': g['name'], 'slug': g.get('slug') or g['name'].lower().replace(' ', '-')})
            type_ = None
            cat = media.get('category')
            if isinstance(cat, dict):
                type_ = cat.get('name')
            elif isinstance(cat, str):
                type_ = cat
            episodes_count = media.get('episodesCount')
            total = int(episodes_count) if episodes_count is not None else None
            return SeriesDetails(title=title, cover=cover, synopsis=synopsis, type=type_, total_episodes=total, genres=genres)

        soup = BeautifulSoup(html, 'html.parser')
        title = slug.replace('-', ' ').title()
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
        cover = None
        img = soup.select_one('img[alt*="Poster" i]') or soup.select_one('img[alt*="%s" i]' % title)
        if img:
            cover = img.get('src') or img.get('data-src')
        if not cover:
            m = re.search(r'https://cdn\.animeav1\.com/covers/[^"\']+', html)
            if m:
                cover = m.group(0)
        if cover and cover.startswith('//'):
            cover = 'https:' + cover
        synopsis = ''
        p = soup.find('p')
        if p and len(p.get_text(strip=True)) > 20:
            synopsis = p.get_text(strip=True)
        return SeriesDetails(title=title, cover=cover, synopsis=synopsis)

    # -----------------------------------------------------------------------
    # Chapters
    # -----------------------------------------------------------------------

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        slug = content_id.strip('/')
        try:
            html = self._fetch_serie_page(slug)
        except Exception as exc:
            logger.exception(f"AnimeAV1 get_chapters error: {exc}")
            return []

        data = self._extract_sveltekit_data(html)
        episodes = []
        if data:
            media = data.get('media') or {}
            episodes = media.get('episodes') or data.get('episodes') or []

        chapters: list[Chapter] = []
        if episodes and isinstance(episodes, list):
            for ep in episodes:
                if isinstance(ep, dict):
                    num = ep.get('number') or ep.get('relativeNumber') or ep.get('id')
                    if num is None:
                        continue
                    chapters.append(Chapter(number=str(num), id=str(num)))
            if chapters:
                chapters.sort(key=lambda x: float(re.sub(r'[^\d\.]', '', x.number) or 0))
                return chapters

        # Fallback: links /media/slug/NUM
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.select('a[href^="/media/%s/"]' % re.escape(slug)):
            href = a.get('href') or ''
            m = re.search(r'/media/%s/(\d+)' % re.escape(slug), href)
            if not m:
                continue
            num = m.group(1)
            chapters.append(Chapter(number=num, id=num))

        # Deduplicate
        uniq = {}
        for c in chapters:
            uniq[c.number] = c
        chapters = list(uniq.values())
        chapters.sort(key=lambda x: float(re.sub(r'[^\d\.]', '', x.number) or 0))
        return chapters

    # -----------------------------------------------------------------------
    # Streaming / Links
    # -----------------------------------------------------------------------

    @property
    def supports_streaming(self) -> bool:
        return True

    def get_stream_url_sync(self, content_id: str, chapter_id: str) -> str | None:
        links = self.get_episode_links(content_id, chapter_id)
        slug = content_id.strip('/')
        ep = str(chapter_id).strip('/')
        # Priorizar SUB, luego cualquier
        for variant in ['SUB', 'DUB']:
            for link in links.stream.get(variant, []):
                url = link.url
                if not url:
                    continue
                if not url.startswith('http'):
                    continue
                # Intentar extraer stream directo de player.zilla-networks
                if 'zilla-networks.com' in url:
                    try:
                        m = re.search(r'/play/([a-f0-9]+)', url)
                        if m:
                            play_id = m.group(1)
                            m3u8_url = f'https://player.zilla-networks.com/m3u8/{play_id}'
                            # Verificar que sea accesible
                            try:
                                r = self._get(m3u8_url, headers={'Referer': f'{self.BASE_URL}/media/{slug}/{ep}'})
                                if r.status_code == 200 and ('#EXTM3U' in r.text or r.text.strip().startswith('#EXT')):
                                    return m3u8_url
                            except Exception:
                                pass
                    except Exception as exc:
                        logger.debug(f'AnimeAV1: fallo extrayendo m3u8 directo: {exc}')
                return url
        return None

    def get_episode_links(self, content_id: str, chapter_id: str) -> EpisodeLinks:
        slug = content_id.strip('/')
        ep = str(chapter_id).strip('/')
        try:
            html = self._fetch_episode_page(slug, ep)
        except Exception as exc:
            logger.exception(f"AnimeAV1 get_episode_links error: {exc}")
            return EpisodeLinks()

        data = self._extract_sveltekit_data(html)
        stream_links: dict[str, list[EpisodeLink]] = {'SUB': [], 'DUB': []}
        download_links: dict[str, list[EpisodeLink]] = {'SUB': [], 'DUB': []}
        seen_s = set()
        seen_d = set()

        if data:
            embeds = data.get('embeds') or {}
            downloads = data.get('downloads') or {}

            for variant in ['SUB', 'DUB']:
                # Embeds
                for item in embeds.get(variant) or []:
                    if isinstance(item, dict):
                        server = item.get('server') or 'Unknown'
                        url = item.get('url') or ''
                        if url and url.startswith('http') and url not in seen_s:
                            seen_s.add(url)
                            stream_links[variant].append(EpisodeLink(server=server, url=url))
                # Downloads
                for item in downloads.get(variant) or []:
                    if isinstance(item, dict):
                        server = item.get('server') or 'Unknown'
                        url = item.get('url') or ''
                        if url and url.startswith('http') and url not in seen_d:
                            seen_d.add(url)
                            download_links[variant].append(EpisodeLink(server=server, url=url))

        # Fallback: buscar iframes
        if not stream_links['SUB'] and not stream_links['DUB']:
            soup = BeautifulSoup(html, 'html.parser')
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src') or ''
                if src.startswith('http') and src not in seen_s:
                    seen_s.add(src)
                    stream_links['SUB'].append(EpisodeLink(server='iframe', url=src))

        return EpisodeLinks(stream=stream_links, download=download_links)

    # -----------------------------------------------------------------------
    # Download
    # -----------------------------------------------------------------------

    def _mp4upload_direct(self, page_url: str) -> str:
        """Resuelve la URL directa de MP4Upload con yt-dlp.

        MP4Upload solo expone el vídeo en su URL /embed-<id>.html; la URL
        corta que publica AnimeAV1 se traduce a ese formato.
        """
        m = re.search(r'mp4upload\.com/(?:embed-)?([a-z0-9]+?)(?:\.html)?/?$', page_url)
        if not m:
            raise Exception(f"MP4Upload: URL no reconocida: {page_url}")
        embed_url = f"https://www.mp4upload.com/embed-{m.group(1)}.html"
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

        direct = (result.stdout or '').strip().split('\n')[0]
        if result.returncode != 0 or not direct.startswith('http'):
            raise Exception(f"MP4Upload: yt-dlp falló: {(result.stderr or '').strip()}")
        JkanimeSource._validate_mp4upload_url(self, direct)
        return direct

    def _download_direct(self, server: str, page_url: str) -> tuple[str, str, str]:
        """Devuelve (url directa, referer, origin) para un servidor de descarga."""
        if server == 'mp4upload':
            return self._mp4upload_direct(page_url), _MP4UPLOAD_REFERER, _MP4UPLOAD_ORIGIN
        m = re.search(r'pixeldrain\.com/u/([\w-]+)', page_url)
        if not m:
            raise Exception(f"Pixeldrain: URL no reconocida: {page_url}")
        return (f"https://pixeldrain.com/api/file/{m.group(1)}?download",
                'https://pixeldrain.com/', 'https://pixeldrain.com')

    def _remote_size(self, url: str, referer: str, origin: str) -> int | None:
        try:
            head = self.scraper.head(url, headers={
                **self._headers,
                'Referer': referer,
                'Origin': origin,
            }, timeout=HTTP_TIMEOUT)
            return int(head.headers.get('content-length') or 0) or None
        except Exception:
            return None

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str,
                              chapter_number: str | None = None, progress_cb=None) -> str:
        links = self.get_episode_links(content_id, chapter_id)
        subs = links.download.get('SUB') or []
        if not subs:
            raise Exception("AnimeAV1: este episodio no tiene enlaces de descarga SUB")

        cap = chapter_to_filename(str(chapter_number or chapter_id), padding=3)
        filepath = os.path.join(dest_folder, f"{cap}.mp4")
        os.makedirs(dest_folder, exist_ok=True)

        # MP4Upload primero; PDrain como alternativa
        candidates = []
        for server in ('mp4upload', 'pixeldrain'):
            match = next((l for l in subs if server in (l.url or '').lower()), None)
            if match:
                candidates.append((server, match.url))
        if not candidates:
            disponible = ', '.join(f"{l.server}: {l.url}" for l in subs)
            raise Exception(f"AnimeAV1: sin servidores soportados (MP4Upload/PDrain). Enlaces: {disponible}")

        last_error = None
        for idx, (server, page_url) in enumerate(candidates):
            if idx and os.path.exists(filepath):
                # No reanudar un parcial con datos de otro servidor
                os.remove(filepath)
            # Token del CDN de corta vida: re-resolver una vez si falla
            for attempt in range(2):
                try:
                    direct, referer, origin = self._download_direct(server, page_url)
                    size = self._remote_size(direct, referer, origin)
                    if size and os.path.exists(filepath) and os.path.getsize(filepath) == size:
                        logger.info(f"AnimeAV1: archivo ya completo, reutilizando: {filepath}")
                        return filepath
                    return JkanimeSource._download_curl(
                        self, direct, filepath,
                        referer=referer,
                        origin=origin,
                        progress_cb=progress_cb,
                    )
                except Exception as exc:
                    last_error = exc
                    logger.warning(f"AnimeAV1: {server} intento {attempt + 1} falló ({exc}), reintentando")
        raise Exception(f"AnimeAV1: no se pudo descargar el capítulo: {last_error}")
