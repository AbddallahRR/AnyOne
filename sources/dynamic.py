import html as _html
import json
import logging
import os
import re
import threading
import time
import urllib.parse
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.database import get_conn
from core.disk_cache import search_cache
from core.html_utils import (
    ATTR_PRIORITY,
    extract_background_images,
    extract_images_from_noscript,
    extract_images_from_scripts,
    extract_items_with_templates,
    normalize_image_url,
    url_ext,
)
from core.http_pool import HTTP_TIMEOUT, HttpPool
from core.chapter_utils import chapter_float_key, normalize_chapter_number
from core.models import Chapter, SearchResult, SeriesDetails, chapter_to_filename
from core.throttle import rate_limiter

from . import BaseSource
from .common import HttpClientMixin

logger = logging.getLogger(__name__)

_REFRESH_COOLDOWN = 86400  # 24 h
_refresh_locks: dict[str, threading.Lock] = {}
_last_refresh_ts: dict[str, float] = {}
_last_errors: dict[str, str] = {}  # CONFIG_NAME -> last error message


def get_last_error(name: str) -> str:
    return _last_errors.get(name, '')


# --- IGNORE --- (base class for generated scrapers, not standalone)

class DynamicSource(HttpClientMixin, BaseSource):
    CONFIG_NAME = ''

    def __init__(self):
        super().__init__()
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
        except Exception as exc:
            logger.warning(f'{self.CONFIG_NAME}: error cargando config desde DB: {exc}')
            self._cfg = {}
        return self._cfg

    def reload_config(self) -> None:
        self._cfg = None
        self._load_config()

    def _set_error(self, msg: str) -> None:
        _last_errors[self.CONFIG_NAME] = msg

    def _clear_error(self) -> None:
        _last_errors.pop(self.CONFIG_NAME, None)

    @property
    def label(self) -> str:
        self._load_config()
        return self._cfg.get('label', self.CONFIG_NAME) if self._cfg else self.CONFIG_NAME

    @property
    def type(self) -> str:
        self._load_config()
        return self._cfg.get('type', '') if self._cfg else ''

    @property
    def BASE_URL(self) -> str:
        self._load_config()
        return self._cfg.get('base_url', '') if self._cfg else ''

    @property
    def UA(self) -> str:
        return ("Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0")

    @property
    def _headers(self) -> dict:
        self._load_config()
        headers = {'User-Agent': self.UA}
        if self._cfg:
            extra = self._cfg.get('config', {}).get('extra_headers', {})
            if isinstance(extra, dict):
                headers.update(extra)
        return headers

    @property
    def _cookies(self) -> dict:
        self._load_config()
        if self._cfg:
            cookies = self._cfg.get('config', {}).get('extra_cookies', {})
            if isinstance(cookies, dict) and cookies:
                return cookies
        return {}

    def _extract_attr(self, soup, selector: str, attr: str = 'text') -> str:
        if not selector:
            return ''
        try:
            elem = soup.select_one(selector)
        except Exception as exc:
            logger.debug(f'{self.CONFIG_NAME}: error en selector CSS: {selector}: {exc}')
            self._set_error(f'Invalid CSS selector: {selector}')
            return ''
        if not elem:
            self._set_error(f'Selector "{selector}" matched no elements')
            return ''
        self._clear_error()
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

    def _apply_pagination(self, url: str, param_name: str, page: int) -> str:
        if not param_name or '{page}' in url:
            return url
        parsed = list(urllib.parse.urlparse(url))
        qs = dict(urllib.parse.parse_qsl(parsed[4]))
        qs[param_name] = str(page)
        parsed[4] = urllib.parse.urlencode(qs)
        return urllib.parse.urlunparse(parsed)

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
            url = self._apply_pagination(
                self._build_url(url_template, page=str(page)),
                pagination_param, page,
            )
            try:
                html = self._get(url).text
            except Exception as exc:
                logger.warning(f"{self.CONFIG_NAME}: catalog page {page} error: {exc}")
                break

            soup = BeautifulSoup(html, 'html.parser')
            items = extract_items_with_templates(soup, item_sel, deduplicate_href=True) if item_sel else [soup]
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

    def _fetch_page(self, url: str, method: str = 'GET', post_template: str = '') -> str:
        """Fetch a page using GET or POST."""
        if method.upper() == 'POST' and post_template:
            data = {}
            for pair in post_template.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    data[k] = v.replace('{query}', '')
            data = {k: (v.replace('{query}', '') if isinstance(v, str) else v) for k, v in data.items()}
            cookies = self._cookies or None
            resp = self.scraper.post(url, headers=self._headers, data=data,
                                     cookies=cookies, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        return self._get(url).text

    def _normalize_cover(self, cover: str) -> str:
        if not cover:
            return ''
        if cover.startswith('//'):
            return 'https:' + cover
        if cover.startswith('/'):
            return urljoin(self.BASE_URL, cover)
        return cover

    def _build_search_urls(self, url_template: str, query: str) -> list[str]:
        """Build search URLs. If search pagination is enabled, generates page URLs.

        Supports two pagination modes:
        1. ``{page}`` placeholder in the URL template itself (e.g. ``/page/{page}/?s={query}``)
        2. Query parameter pagination via *search_pagination_param* (e.g. ``?page=2``)
        """
        cfg = self._load_config().get('config', {})
        urls: list[str] = []
        if cfg.get('search_has_pagination'):
            part_name = cfg.get('search_pagination_param', 'page')
            for page in range(1, 101):
                url = self._apply_pagination(
                    self._build_url(url_template, query=query, page=str(page)),
                    part_name, page,
                )
                urls.append(url)
        else:
            urls.append(self._build_url(url_template, query=query, page='1'))
        return urls

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

        # Try cached results first (non-catalog mode)
        cache_ttl = int(cfg.get('search_cache_ttl', 0))
        cache_key = f"{self.CONFIG_NAME}:search:{query.lower().strip()}"
        if cache_ttl > 0:
            cached = search_cache.get(cache_key)
            if cached is not None:
                return [SearchResult(**r) for r in cached]

        search_method = cfg.get('search_method', 'GET')
        search_post_template = cfg.get('search_post_template', '')
        result_sel = cfg.get('search_result_selector', '')
        title_sel = cfg.get('search_title_selector', '')
        title_attr = cfg.get('search_title_attr', 'text')
        url_sel = cfg.get('search_url_selector', '')
        url_attr = cfg.get('search_url_attr', 'href')
        cover_sel = cfg.get('search_cover_selector', '')
        cover_attr = cfg.get('search_cover_attr', 'src')

        seen = set()
        results = []
        urls = self._build_search_urls(url_template, query)

        for url in urls:
            try:
                if search_method.upper() == 'POST' and search_post_template:
                    filled_template = search_post_template.replace('{query}', query)
                    html = self._fetch_page(url, 'POST', filled_template)
                else:
                    html = self._get(url).text
            except Exception as exc:
                logger.exception(f"{self.CONFIG_NAME} search error: {exc}")
                self._set_error(f'Search fetch error: {exc}')
                break

            soup = BeautifulSoup(html, 'html.parser')
            cards = extract_items_with_templates(soup, result_sel, deduplicate_href=True) if result_sel else [soup]

            page_results = 0
            for card in cards:
                title = self._extract_attr(card, title_sel, title_attr) if title_sel else ''
                href = self._extract_attr(card, url_sel, url_attr) if url_sel else ''
                if not href and card.name == 'a':
                    href = card.get('href', '')
                cover = self._extract_attr(card, cover_sel, cover_attr) if cover_sel else ''

                if not title:
                    continue

                content_id = href.rstrip('/').split('/')[-1] if href else title
                key = (content_id, title)
                if key in seen:
                    continue
                seen.add(key)

                results.append(SearchResult(
                    id=content_id,
                    title=title,
                    cover=self._normalize_cover(cover),
                ))
                page_results += 1

            if not cfg.get('search_has_pagination') or page_results == 0:
                break

        # Cache results if TTL configured
        if cache_ttl > 0 and results:
            search_cache.set(
                cache_key,
                [r.model_dump() for r in results],
                ttl=cache_ttl,
            )

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

        return SeriesDetails(title=title, cover=self._normalize_cover(cover), synopsis=synopsis)

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

        seen = set()
        all_chapters = []
        page = 1
        while True:
            url = self._apply_pagination(
                self._build_url(url_template, content_id=content_id, page=str(page)),
                part_name, page,
            )
            try:
                html = self._get(url).text
            except Exception as exc:
                if page == 1:
                    logger.exception(f"{self.CONFIG_NAME} chapters error: {exc}")
                break

            soup = BeautifulSoup(html, 'html.parser')
            items = extract_items_with_templates(soup, item_sel, deduplicate_href=True) if item_sel else [soup]

            page_chapters = 0
            for item in items:
                num = self._extract_attr(item, num_sel, num_attr) if num_sel else ''
                href = self._extract_attr(item, url_sel, url_attr) if url_sel else ''
                if not href and item.name == 'a':
                    href = item.get('href', '')
                if not num:
                    continue
                nums = re.findall(r'\d+(?:\.\d+)?', num)
                num = normalize_chapter_number(nums[0]) if nums else num
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

        all_chapters.sort(key=lambda x: chapter_float_key(x.number))
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
        base_url = self.BASE_URL

        seen: set[str] = set()
        urls: list[str] = []

        def _add(norm_url):
            if norm_url and norm_url not in seen:
                seen.add(norm_url)
                urls.append(norm_url)

        # Strategy 1: CSS selector + configured attribute
        if img_sel:
            for img in soup.select(img_sel):
                src = img.get(img_attr) or img.get('src')
                if src:
                    _add(normalize_image_url(src, base_url))
            if urls:
                return urls

        # Strategy 2: CSS selector + try all priority attrs
        if img_sel:
            for attr_name in ATTR_PRIORITY:
                if attr_name == img_attr:
                    continue
                batch = []
                for img in soup.select(img_sel):
                    src = img.get(attr_name) or img.get('src')
                    if src:
                        norm = normalize_image_url(src, base_url)
                        if norm:
                            batch.append(norm)
                if batch:
                    for n in batch:
                        _add(n)
                    if urls:
                        logger.info(f'{self.CONFIG_NAME}: images found via {attr_name} (fallback attr)')
                        return urls

        # Strategy 3: <noscript> extraction
        noscript_imgs = extract_images_from_noscript(soup)
        for entry in noscript_imgs:
            _add(normalize_image_url(entry['src'], base_url))
        if urls:
            logger.info(f'{self.CONFIG_NAME}: images found via <noscript>')
            return urls

        # Strategy 4: JS script extraction
        script_urls = extract_images_from_scripts(soup, base_url)
        for u in script_urls:
            _add(normalize_image_url(u, base_url))
        if urls:
            logger.info(f'{self.CONFIG_NAME}: images found via JS scripts')
            return urls

        # Strategy 5: CSS background-image
        bg_urls = extract_background_images(soup, img_sel or '')
        for u in bg_urls:
            _add(normalize_image_url(u, base_url))
        if urls:
            logger.info(f'{self.CONFIG_NAME}: images found via CSS background-image')
            return urls

        # Strategy 6: Any <img> with any src-like attribute (last resort)
        for img in soup.find_all('img'):
            for attr_name in ATTR_PRIORITY:
                src = img.get(attr_name)
                if src:
                    norm = normalize_image_url(src, base_url)
                    if norm:
                        _add(norm)
                        break
            if urls:
                break

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
        except Exception as exc:
            logger.warning(f'{self.CONFIG_NAME}: error obteniendo pagina de video: {url}: {exc}')
            return None

        vid_sel = cfg.get('content_video_selector', '')
        vid_attr = cfg.get('content_video_attr', 'src')
        if vid_sel:
            soup = BeautifulSoup(resp.text, 'html.parser')
            return self._extract_attr(soup, vid_sel, vid_attr) or None
        return None

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str,
                              chapter_number: str | None = None, progress_cb=None) -> str:
        cfg = self._load_config().get('config', {})
        if cfg.get('content_type') == 'image':
            return self._download_images(content_id, chapter_id, dest_folder,
                                         chapter_number, progress_cb)
        raise NotImplementedError(
            f"{self.CONFIG_NAME}: download not supported for content_type={cfg.get('content_type')}"
        )

    def _download_images(self, content_id: str, chapter_id: str, dest_folder: str,
                         chapter_number: str | None = None, progress_cb=None) -> str:
        import concurrent.futures

        img_urls = self.get_chapter_images_sync(content_id, chapter_id)
        if not img_urls:
            raise Exception(f"{self.CONFIG_NAME}: no images found for chapter {chapter_id}")

        cap_num = chapter_number or chapter_id
        if cap_num.replace('.', '', 1).isdigit():
            dir_name = f"cap_{chapter_to_filename(cap_num)}"
        else:
            dir_name = f"cap_{cap_num}"
        cap_dir = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)

        cfg = self._load_config().get('config', {})
        max_workers = min(cfg.get('download_concurrency', 4), 10)

        def _download_one(args):
            i, img_url = args
            ext = url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                return True
            try:
                rate_limiter.wait(img_url)
                cookies = self._cookies or None
                with HttpPool.get_session().get(
                    img_url,
                    headers={**self._headers, 'Referer': self.BASE_URL},
                    cookies=cookies,
                    timeout=HTTP_TIMEOUT,
                    stream=True,
                ) as resp:
                    resp.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                return True
            except Exception as exc:
                logger.warning(f"{self.CONFIG_NAME}: error downloading image {i}: {exc}")
                return False

        tasks = list(enumerate(img_urls, start=1))
        failures = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, success in enumerate(pool.imap(_download_one, tasks), start=1):
                if not success:
                    failures += 1
                if progress_cb:
                    progress_cb(i, len(tasks), f'Imagen {i}/{len(tasks)}')

        if failures:
            logger.warning(f"{self.CONFIG_NAME}: {failures}/{len(img_urls)} images failed to download")

        return cap_dir
