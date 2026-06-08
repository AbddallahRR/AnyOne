import json
import logging
import os
import re
import threading
import time
import urllib.parse
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from core.database import get_conn
from core.disk_cache import search_cache
from core.http_pool import HttpPool
from core.models import Chapter, SearchResult, SeriesDetails
from core.throttle import rate_limiter

from . import BaseSource

logger = logging.getLogger(__name__)

_TIMEOUT = 30

_REFRESH_COOLDOWN = 86400  # 24 h
_refresh_locks: dict[str, threading.Lock] = {}
_last_refresh_ts: dict[str, float] = {}


# --- IGNORE --- (base class for generated scrapers, not standalone)

class DynamicSource(BaseSource):
    CONFIG_NAME = ''

    def __init__(self):
        self.scraper = HttpPool.get_scraper()
        self._cfg = None

    def _load_config(self) -> dict:
        if self._cfg is not None:
            return self._cfg
        try:
            conn = get_conn()
            row = conn.execute(
                'SELECT type, label, base_url, config_json FROM scraper_configs WHERE name = ?',
                (self.CONFIG_NAME,)
            ).fetchone()
            if not row:
                self._cfg = {}
                return self._cfg
            self._cfg = {
                'type': row['type'],
                'label': row['label'],
                'base_url': row['base_url'],
            }
            try:
                self._cfg['config'] = json.loads(row['config_json'])
            except (json.JSONDecodeError, TypeError):
                self._cfg['config'] = {}
        except Exception:
            logger.warning(f'{self.CONFIG_NAME}: error cargando config desde DB')
            self._cfg = {}
        return self._cfg

    @property
    def label(self) -> str:
        return self._load_config().get('label', self.CONFIG_NAME)

    @property
    def type(self) -> str:
        return self._load_config().get('type', '')

    @property
    def BASE_URL(self) -> str:
        return self._load_config().get('base_url', '')

    @property
    def UA(self) -> str:
        return ("Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0")

    @property
    def _headers(self) -> dict:
        cfg = self._load_config()
        headers = {'User-Agent': self.UA}
        extra = cfg.get('config', {}).get('extra_headers', {})
        headers.update(extra)
        return headers

    def _get(self, url: str, **kwargs):
        rate_limiter.wait(url)
        kwargs.setdefault('timeout', _TIMEOUT)
        headers = self._headers.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        scraper = HttpPool.get_scraper()
        resp = scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> dict:
        return self._get(url, **kwargs).json()

    def _extract_attr(self, soup, selector: str, attr: str = 'text') -> str:
        if not selector:
            return ''
        try:
            elem = soup.select_one(selector)
        except Exception:
            logger.debug(f'{self.CONFIG_NAME}: error en selector CSS: {selector}')
            return ''
        if not elem:
            return ''
        if attr == 'text':
            text = elem.get_text(strip=True)
            if not text:
                text = ''.join(str(c) for c in elem.children if isinstance(c, str))
                text = text.strip()
            return text
        return elem.get(attr, '')

    def _extract_attrs(self, soup, selector: str, attr: str = 'text') -> list[str]:
        if not selector:
            return []
        result = []
        for elem in soup.select(selector):
            if attr == 'text':
                result.append(elem.get_text(strip=True))
            else:
                val = elem.get(attr, '')
                if val:
                    result.append(val)
        return result

    def _build_url(self, template: str, **kwargs) -> str:
        base = self.BASE_URL.rstrip('/')
        url = template.replace('{base}', base)
        for key, value in kwargs.items():
            url = url.replace(f'{{{key}}}', str(value))
        return url

    # ── Catalog / warm cache ────────────────────────────────────────────

    def warm_cache_sync(self) -> None:
        cfg = self._load_config().get('config', {})
        if not cfg.get('has_catalog'):
            return
        cache_key = f"{self.CONFIG_NAME}:catalog"
        if search_cache.get(cache_key) is not None:
            return
        t = threading.Thread(target=self._build_catalog, daemon=True)
        t.start()

    def _build_catalog(self) -> None:
        cfg = self._load_config().get('config', {})
        if not cfg.get('has_catalog'):
            return

        url_template = cfg.get('catalog_url_template', '')
        if not url_template:
            return

        item_sel = cfg.get('catalog_item_selector', '')
        title_sel = cfg.get('catalog_title_selector', '')
        title_attr = cfg.get('catalog_title_attr', 'text')
        url_sel = cfg.get('catalog_url_selector', '')
        url_attr = cfg.get('catalog_url_attr', 'href')
        cover_sel = cfg.get('catalog_cover_selector', '')
        cover_attr = cfg.get('catalog_cover_attr', 'src')
        pagination_param = cfg.get('catalog_pagination_param', 'page')
        max_pages = int(cfg.get('catalog_max_pages', 100))
        cache_ttl = int(cfg.get('catalog_cache_ttl', 259200))

        all_items: list[dict] = []
        page = 1
        while page <= max_pages:
            url = self._build_url(url_template, page=str(page))
            if pagination_param and '{page}' not in url_template:
                parsed = list(urllib.parse.urlparse(url))
                qs = dict(urllib.parse.parse_qsl(parsed[4]))
                qs[pagination_param] = str(page)
                parsed[4] = urllib.parse.urlencode(qs)
                url = urllib.parse.urlunparse(parsed)
            try:
                html = self._get(url).text
            except Exception as exc:
                logger.warning(f"{self.CONFIG_NAME}: catalog page {page} error: {exc}")
                break

            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select(item_sel) if item_sel else [soup]
            page_items = 0
            for item in items:
                title = self._extract_attr(item, title_sel, title_attr) if title_sel else ''
                href = self._extract_attr(item, url_sel, url_attr) if url_sel else ''
                if not href and item.name == 'a':
                    href = item.get('href', '')
                cover = self._extract_attr(item, cover_sel, cover_attr) if cover_sel else ''
                if not title:
                    continue
                content_id = href.rstrip('/').split('/')[-1] if href else title
                if cover and cover.startswith('//'):
                    cover = 'https:' + cover
                elif cover and cover.startswith('/'):
                    cover = urljoin(self.BASE_URL, cover)
                all_items.append({'id': content_id, 'title': title, 'cover': cover})
                page_items += 1

            if page_items == 0:
                break
            page += 1

        if all_items:
            search_cache.set(f"{self.CONFIG_NAME}:catalog", all_items, ttl=cache_ttl)
            logger.info(f"{self.CONFIG_NAME}: catalog built with {len(all_items)} items")

    def _refresh_catalog_background(self) -> None:
        name = self.CONFIG_NAME
        now = time.time()
        if now - _last_refresh_ts.get(name, 0) < _REFRESH_COOLDOWN:
            return
        lock = _refresh_locks.setdefault(name, threading.Lock())
        if not lock.acquire(blocking=False):
            return
        try:
            cache_key = f"{name}:catalog"
            search_cache.delete(cache_key)
            self._build_catalog()
            _last_refresh_ts[name] = time.time()
        finally:
            lock.release()

    def search_sync(self, query: str) -> list[SearchResult]:
        cfg = self._load_config().get('config', {})

        # If has_catalog, search from cached catalog instead of live HTTP
        if cfg.get('has_catalog'):
            cache_key = f"{self.CONFIG_NAME}:catalog"
            catalog = search_cache.get(cache_key)
            if catalog is None:
                self._build_catalog()
                catalog = search_cache.get(cache_key) or []
            else:
                self._refresh_catalog_background()

            query_lower = query.lower().strip()
            results = []
            for item in catalog:
                if query_lower in item.get('title', '').lower():
                    results.append(SearchResult(
                        id=item['id'],
                        title=item['title'],
                        cover=item.get('cover', ''),
                    ))
            return results

        url_template = cfg.get('search_url_template', '')
        if not url_template:
            return []

        url = self._build_url(url_template, query=query)
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.exception(f"{self.CONFIG_NAME} search error: {exc}")
            return []

        soup = BeautifulSoup(html, 'html.parser')
        result_sel = cfg.get('search_result_selector', '')
        title_sel = cfg.get('search_title_selector', '')
        title_attr = cfg.get('search_title_attr', 'text')
        url_sel = cfg.get('search_url_selector', '')
        url_attr = cfg.get('search_url_attr', 'href')
        cover_sel = cfg.get('search_cover_selector', '')
        cover_attr = cfg.get('search_cover_attr', 'src')

        results = []
        for card in soup.select(result_sel) if result_sel else [soup]:
            title = self._extract_attr(card, title_sel, title_attr) if title_sel else ''
            href = ''
            if url_sel:
                href = self._extract_attr(card, url_sel, url_attr)
            if not href and card.name == 'a':
                href = card.get('href', '')
            cover = self._extract_attr(card, cover_sel, cover_attr) if cover_sel else ''

            if not title:
                continue

            content_id = href.rstrip('/').split('/')[-1] if href else title
            if cover and cover.startswith('//'):
                cover = 'https:' + cover
            elif cover and cover.startswith('/'):
                cover = urljoin(self.BASE_URL, cover)

            results.append(SearchResult(id=content_id, title=title, cover=cover))

        return results

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        cfg = self._load_config().get('config', {})
        url_template = cfg.get('details_url_template', '')
        if not url_template:
            return SeriesDetails(title=content_id)

        url = self._build_url(url_template, content_id=content_id)
        try:
            html = self._get(url).text
        except Exception as exc:
            logger.exception(f"{self.CONFIG_NAME} details error: {exc}")
            return SeriesDetails(title=content_id)

        soup = BeautifulSoup(html, 'html.parser')

        title_sel = cfg.get('details_title_selector', '')
        title_attr = cfg.get('details_title_attr', 'text')
        cover_sel = cfg.get('details_cover_selector', '')
        cover_attr = cfg.get('details_cover_attr', 'src')
        synopsis_sel = cfg.get('details_synopsis_selector', '')

        title = self._extract_attr(soup, title_sel, title_attr) if title_sel else content_id
        cover = self._extract_attr(soup, cover_sel, cover_attr) if cover_sel else ''
        synopsis = self._extract_attr(soup, synopsis_sel) if synopsis_sel else ''

        if cover and cover.startswith('//'):
            cover = 'https:' + cover
        elif cover and cover.startswith('/'):
            cover = urljoin(self.BASE_URL, cover)

        return SeriesDetails(title=title, cover=cover, synopsis=synopsis)

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        cfg = self._load_config().get('config', {})
        url_template = cfg.get('chapters_url_template', '')
        if not url_template:
            return []

        part_name = cfg.get('pagination_param', '') if cfg.get('has_pagination') else ''
        item_sel = cfg.get('chapters_item_selector', '')
        num_sel = cfg.get('chapters_num_selector', '')
        num_attr = cfg.get('chapters_num_attr', 'text')
        url_sel = cfg.get('chapters_url_selector', '')
        url_attr = cfg.get('chapters_url_attr', 'href')

        base_url = self._build_url(url_template, content_id=content_id)
        seen = set()
        all_chapters = []
        page = 1
        while True:
            url = base_url
            if part_name:
                parsed = list(urllib.parse.urlparse(url))
                qs = dict(urllib.parse.parse_qsl(parsed[4]))
                qs[part_name] = str(page)
                parsed[4] = urllib.parse.urlencode(qs)
                url = urllib.parse.urlunparse(parsed)
            try:
                html = self._get(url).text
            except Exception as exc:
                if page == 1:
                    logger.exception(f"{self.CONFIG_NAME} chapters error: {exc}")
                break

            soup = BeautifulSoup(html, 'html.parser')
            items = []
            if item_sel:
                try:
                    items = soup.select(item_sel)
                except Exception:
                    logger.debug(f'{self.CONFIG_NAME}: error en selector CSS de capitulos: {item_sel}')
                    items = []
                for tmpl in soup.find_all('template'):
                    found = tmpl.select(item_sel) if item_sel else []
                    if not found and items:
                        found = tmpl.find_all(items[0].name)
                    items.extend(found)
            else:
                items = [soup]

            page_chapters = 0
            for item in items:
                num = self._extract_attr(item, num_sel, num_attr) if num_sel else ''
                href = self._extract_attr(item, url_sel, url_attr) if url_sel else ''
                if not href and item.name == 'a':
                    href = item.get('href', '')
                if not num:
                    continue
                nums = re.findall(r'\d+(?:\.\d+)?', num)
                num = nums[0] if nums else num
                parts = num.split('.')
                parts[0] = parts[0].lstrip('0') or '0'
                num = '.'.join(parts)
                chap_id = href.rstrip('/').split('/')[-1] if href else num
                key = (num, chap_id)
                if key in seen:
                    continue
                seen.add(key)
                all_chapters.append(Chapter(number=num, id=chap_id))
                page_chapters += 1

            if not part_name or page_chapters == 0:
                break
            page += 1

        all_chapters.sort(key=lambda x: float(x.number) if x.number.replace('.', '', 1).isdigit() else 0)
        return all_chapters

    def get_chapter_images_sync(self, content_id: str, chapter_id: str) -> list[str]:
        cfg = self._load_config().get('config', {})
        if cfg.get('content_type') != 'image':
            return []

        tmpl = cfg.get('content_page_template', '')
        if not tmpl:
            return []

        url = self._build_url(tmpl, content_id=content_id, chapter_id=chapter_id)
        try:
            resp = self._get(url)
        except Exception as exc:
            logger.exception(f"{self.CONFIG_NAME} chapter images error: {exc}")
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        img_sel = cfg.get('content_image_selector', '')
        img_attr = cfg.get('content_image_attr', 'src')

        seen = set()
        urls = []
        for img in soup.select(img_sel):
            src = img.get(img_attr) or img.get('src')
            if src:
                norm = self._normalize_url(src)
                if norm and norm not in seen:
                    seen.add(norm)
                    urls.append(norm)
        return urls

    @property
    def supports_streaming(self) -> bool:
        cfg = self._load_config().get('config', {})
        return cfg.get('content_type') == 'video'

    def get_stream_url_sync(self, content_id: str, chapter_id: str) -> str | None:
        cfg = self._load_config().get('config', {})
        if cfg.get('content_type') != 'video':
            return None

        tmpl = cfg.get('content_page_template', '')
        if not tmpl:
            return None

        url = self._build_url(tmpl, content_id=content_id, chapter_id=chapter_id)
        try:
            resp = self._get(url)
        except Exception:
            logger.warning(f'{self.CONFIG_NAME}: error obteniendo pagina de video: {url}')
            return None

        vid_sel = cfg.get('content_video_selector', '')
        vid_attr = cfg.get('content_video_attr', 'src')
        if vid_sel:
            soup = BeautifulSoup(resp.text, 'html.parser')
            return self._extract_attr(soup, vid_sel, vid_attr) or None
        return None

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str, chapter_number: str | None = None) -> str:
        cfg = self._load_config().get('config', {})
        if cfg.get('content_type') == 'image':
            return self._download_images(content_id, chapter_id, dest_folder, chapter_number)
        raise NotImplementedError(
            f"{self.CONFIG_NAME}: download not supported for content_type={cfg.get('content_type')}"
        )

    def _download_images(self, content_id: str, chapter_id: str, dest_folder: str, chapter_number: str | None = None) -> str:
        img_urls = self.get_chapter_images_sync(content_id, chapter_id)
        if not img_urls:
            raise Exception(f"{self.CONFIG_NAME}: no images found for chapter {chapter_id}")

        cap_num = chapter_number or chapter_id
        if cap_num.replace('.', '', 1).isdigit():
            dir_name = f"cap_{int(float(cap_num)):04d}"
        else:
            dir_name = f"cap_{cap_num}"
        cap_dir = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        for i, img_url in enumerate(img_urls, start=1):
            ext = self._url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                continue
            try:
                rate_limiter.wait(img_url)
                with HttpPool.get_session().get(
                    img_url,
                    headers={**self._headers, 'Referer': self.BASE_URL},
                    timeout=_TIMEOUT,
                    stream=True,
                ) as resp:
                    resp.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
            except Exception as exc:
                logger.warning(f"{self.CONFIG_NAME}: error downloading image {i}: {exc}")

        return cap_dir

    def _normalize_url(self, src: str) -> str | None:
        if not src or src.startswith('data:'):
            return None
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            base = self.BASE_URL.rstrip('/')
            src = base + '/' + src.lstrip('/')
        lower = src.lower()
        if any(x in lower for x in ('loading', 'placeholder', 'blank.', 'spinner')):
            return None
        return src

    @staticmethod
    def _url_ext(url: str) -> str:
        path = urlparse(url).path
        ext = os.path.splitext(path)[1].lstrip('.')
        if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
            m = re.search(r'[?&]format=(jpg|jpeg|png|webp)', url, re.I)
            ext = m.group(1) if m else 'jpg'
        return ext
