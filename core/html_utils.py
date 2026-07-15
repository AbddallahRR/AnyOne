import copy
import html as _html
import json as _json
import logging
import os
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# Ordered list of image attributes to try, highest priority first
ATTR_PRIORITY = [
    'data-lm-orig-src',
    'data-original',
    'data-lazy-src',
    'data-url',
    'data-src',
    'data-echo',
    'data-cfsrc',
    'data-src-retina',
    'data-srcset',
    'data-lazy',
    'data-image',
    'data-img',
    'src',
]

# Patterns to ignore in image URLs (lowercased)
SKIP_URL_PATTERNS = [
    'loading', 'placeholder', 'blank.', 'spinner',
    '1x1', 'pixel', 'transparent', 'clear.gif',
    'icon', 'logo', 'avatar', 'banner', 'thumb-tiny',
    'data:image/svg', 'data:image/gif;base64',
]


def validate_css_selector(selector: str) -> bool:
    """Check if a CSS selector is syntactically valid by trying to parse it
    with BeautifulSoup on a minimal document."""
    if not selector:
        return True
    try:
        soup = BeautifulSoup('<html><body></body></html>', 'html.parser')
        soup.select_one(selector)
        return True
    except Exception:
        return False


def _get_item_href(item: Tag) -> str:
    """Try to extract an href from an item: direct attribute, first ``<a>`` child,
    or common data-attributes."""
    if hasattr(item, 'get'):
        href = item.get('href', '')
        if href:
            return href
        a_tag = item.find('a', href=True)
        if a_tag:
            return a_tag.get('href', '')
        for attr in ('data-id', 'data-url', 'data-href', 'data-key'):
            val = item.get(attr, '')
            if val:
                return val
    return ''


def extract_items_with_templates(
    soup: BeautifulSoup,
    selector: str,
    deduplicate_href: bool = True,
) -> list[Tag]:
    """Extract elements matching *selector*, including those inside
    ``<template>`` tags (for sites that use "load more" patterns).

    When *deduplicate_href* is True, items from templates are only added
    if their ``href`` is not already present in the main items (tries
    direct href, first ``<a>`` child, and common data-attributes).

    Works by: selecting from a copy of the soup with ``<template>`` tags
    stripped for the main items, then extracting from each ``<template>``
    separately for the hidden items.
    """
    if not selector:
        return [soup]

    items: list[Tag] = []
    tmpl_items: list[Tag] = []

    # Extract items from each <template> first
    for tmpl in soup.find_all('template'):
        try:
            found = tmpl.select(selector)
        except Exception:
            found = []
        if not found:
            first_items = soup.select(selector)
            if first_items:
                found = tmpl.find_all(first_items[0].name)
        tmpl_items.extend(found)

    # Extract main items from a copy with <template> tags removed
    try:
        soup_copy = copy.copy(soup)
        for tmpl in soup_copy.find_all('template'):
            tmpl.decompose()
        items = soup_copy.select(selector)
    except Exception as exc:
        logger.debug(f'CSS selector error: {selector} — {exc}')
        return items

    # Merge template items with deduplication
    if tmpl_items:
        if deduplicate_href:
            seen_hrefs = set()
            for item in items:
                href = _get_item_href(item)
                if href:
                    seen_hrefs.add(href)
            for item in tmpl_items:
                href = _get_item_href(item)
                if href and href not in seen_hrefs:
                    items.append(item)
                    seen_hrefs.add(href)
                elif not href:
                    items.append(item)
        else:
            items.extend(tmpl_items)

    return items


def normalize_image_url(url: str, base_url: str) -> str | None:
    """Normalize and filter an image URL. Returns None if it's a placeholder."""
    if not url or url.startswith('data:'):
        return None
    if url.startswith('//'):
        url = 'https:' + url
    elif url.startswith('/'):
        parsed = urlparse(base_url)
        root = f'{parsed.scheme}://{parsed.netloc}'
        url = root.rstrip('/') + '/' + url.lstrip('/')
    lower = url.lower()
    if any(p in lower for p in SKIP_URL_PATTERNS):
        return None
    return url


def extract_images_from_noscript(soup: BeautifulSoup) -> list[dict]:
    """Extract <img> elements from inside <noscript> tags.

    Returns list of dicts with keys: element (Tag), src (str), attrs (dict)
    """
    results: list[dict] = []
    seen_srcs: set[str] = set()
    for noscript in soup.find_all('noscript'):
        try:
            inner = BeautifulSoup(noscript.decode_contents(), 'html.parser')
            for img in inner.find_all('img'):
                src = img.get('src') or ''
                for attr in ATTR_PRIORITY:
                    val = img.get(attr)
                    if val:
                        src = val
                        break
                if src and src not in seen_srcs:
                    seen_srcs.add(src)
                    results.append({
                        'element': img,
                        'src': src,
                        'attrs': {a: img.get(a) or '' for a in ATTR_PRIORITY if img.get(a)},
                    })
        except Exception:
            continue
    return results


_IMAGE_URL_RE = re.compile(
    r'https?://[^\s"\'\\]+\.(?:jpg|jpeg|png|webp|gif)(?:\?[^\s"\'\\]*)?',
    re.IGNORECASE,
)

_SSR_STATE_RE = re.compile(
    r'window\.(__\w+__)\s*=\s*(\{.+?\})\s*;',
    re.DOTALL,
)

_IMAGE_ARRAY_VAR_RE = re.compile(
    r'(?:var|const|let)\s+'
    r'(?:chapterImages|images|imgUrls|pageImages|chapter_images|manga_images|'
    r'imageList|pageList|chapterPages|pages|srcList|fileList|items)\s*'
    r'=\s*(\[.+?\])\s*;',
    re.DOTALL | re.IGNORECASE,
)

_JSON_PARSE_RE = re.compile(
    r'JSON\.parse\s*\(\s*[\'"](.+?)[\'"]\s*\)',
    re.DOTALL,
)

_IMAGE_KEY_OBJ_RE = re.compile(
    r'(?:["\']?(?:images|pages|chapter_images|pageList|imgList|fileList|srcList)["\']?\s*:\s*)(\[(?:"[^"]*"|\'[^\']*\')(?:\s*,\s*(?:"[^"]*"|\'[^\']*\'))*\])',
    re.DOTALL,
)


def _collect_url(url: str, base_url: str, urls: list[str], seen: set[str]) -> None:
    norm = normalize_image_url(url, base_url)
    if norm and norm not in seen:
        seen.add(norm)
        urls.append(norm)


def _walk_json(obj, urls: list[str], seen: set[str], base_url: str, depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_json(v, urls, seen, base_url, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _walk_json(v, urls, seen, base_url, depth + 1)
    elif isinstance(obj, str):
        if _IMAGE_URL_RE.search(obj):
            _collect_url(obj, base_url, urls, seen)


def _try_parse_json(raw: str) -> object | None:
    try:
        return _json.loads(raw)
    except Exception:
        return None


def extract_images_from_scripts(soup: BeautifulSoup, base_url: str = '') -> list[str]:
    """Extract image URLs from JavaScript blocks in the page.

    Handles:
    - ts_reader.run() / ts_reader_data() JSON config
    - SSR state objects (window.__INITIAL_STATE__, __NUXT__, __NEXT_DATA__, etc.)
    - Generic variable assignments with image URL arrays
    - JSON.parse(...) containing image URLs
    - Inline objects with image/page keys
    - Qwik JSON (<script type="qwik/json">)
    - WordPress madara_* variables
    - Image URL regex fallback across all scripts
    """
    urls: list[str] = []
    seen: set[str] = set()

    for script in soup.find_all('script'):
        text = script.string or ''
        if not text.strip():
            continue

        # ts_reader.run() / ts_reader_data()
        if 'ts_reader.run' in text or 'ts_reader_data' in text:
            match = re.search(
                r'(?:ts_reader\.run|ts_reader_data)\s*\(\s*(\{.+?\})\s*\)\s*;',
                text, re.DOTALL,
            )
            if match:
                data = _try_parse_json(_html.unescape(match.group(1)).replace('\\/', '/'))
                if isinstance(data, dict):
                    for src_group in data.get('sources', []):
                        if isinstance(src_group, dict):
                            for img_url in src_group.get('images', []):
                                _collect_url(img_url, base_url, urls, seen)

        # Qwik JSON (<script type="qwik/json">)
        if script.get('type') == 'qwik/json':
            for m in _IMAGE_URL_RE.finditer(script.string or ''):
                _collect_url(m.group(0), base_url, urls, seen)

        # SSR state objects: window.__INITIAL_STATE__, __NUXT__, __NEXT_DATA__,
        # __APP_STATE__, __PRELOADED_STATE__, __SERVER_DATA__, __APOLLO_STATE__,
        # __INITIAL_PROPS__, __remixContext, __APP_DATA__
        for m in _SSR_STATE_RE.finditer(text):
            var_name = m.group(1)
            data = _try_parse_json(m.group(2))
            if data is not None:
                _walk_json(data, urls, seen, base_url)

        # Generic variable arrays: var images = [...], const chapterPages = [...]
        for m in _IMAGE_ARRAY_VAR_RE.finditer(text):
            data = _try_parse_json(m.group(1))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        _collect_url(item, base_url, urls, seen)

        # JSON.parse("...") — unescaped JSON string with image arrays
        for m in _JSON_PARSE_RE.finditer(text):
            raw = m.group(1).replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
            data = _try_parse_json(raw)
            if data is not None:
                _walk_json(data, urls, seen, base_url)

        # Inline objects with image/page key arrays:
        # { "images": ["url1", "url2"] } or { pages: ['url1'] }
        for m in _IMAGE_KEY_OBJ_RE.finditer(text):
            data = _try_parse_json(m.group(1))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        _collect_url(item, base_url, urls, seen)

        # WordPress Madara: madara_* variables
        for m in re.finditer(r'madara_\w+\s*=\s*["\']([^"\']+)["\']', text):
            u = m.group(1)
            if _IMAGE_URL_RE.search(u):
                _collect_url(u, base_url, urls, seen)

        # Broad fallback: find any image-like URLs in the entire script text
        if not urls:
            for m in _IMAGE_URL_RE.finditer(text):
                _collect_url(m.group(0), base_url, urls, seen)

    return urls


def extract_background_images(soup: BeautifulSoup, selector: str) -> list[str]:
    """Extract image URLs from CSS background-image on elements matching selector."""
    urls: list[str] = []
    seen: set[str] = set()
    elements = soup.select(selector) if selector else soup.find_all(True)
    pattern = re.compile(r"url\(['\"]?(.+?)['\"]?\)")
    for el in elements:
        style = el.get('style', '') or ''
        for match in pattern.finditer(style):
            u = match.group(1).strip().strip("'\"")
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        # Also check computed bg attributes
        for attr in ('data-background', 'data-bg', 'data-image-url'):
            val = el.get(attr, '') or ''
            if val and val not in seen:
                seen.add(val)
                urls.append(val)
    return urls


def extract_from_srcset(element: Tag) -> str:
    """Extract the largest image URL from a srcset or data-srcset attribute."""
    srcset = element.get('srcset') or element.get('data-srcset') or ''
    if not srcset:
        return element.get('src', '') or ''
    candidates: list[tuple[int, str]] = []
    for part in srcset.split(','):
        part = part.strip()
        if not part:
            continue
        parts = part.split()
        url = parts[0] if parts else ''
        if not url:
            continue
        width = 0
        if len(parts) > 1:
            w_match = re.search(r'(\d+)w', parts[1])
            if w_match:
                width = int(w_match.group(1))
            else:
                x_match = re.search(r'(\d+(?:\.\d+)?)x', parts[1])
                if x_match:
                    width = int(float(x_match.group(1)) * 100)
        candidates.append((width, url))
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1] if candidates else (element.get('src', '') or '')


def normalize_url(url: str, base_url: str) -> str:
    """Normalize a URL relative to *base_url*."""
    if not url or url.startswith('data:'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        parsed = urlparse(base_url)
        root = f'{parsed.scheme}://{parsed.netloc}'
        return root.rstrip('/') + '/' + url.lstrip('/')
    return urljoin(base_url.rstrip('/') + '/', url)


def url_ext(url: str, default: str = 'jpg') -> str:
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lstrip('.')
    if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
        m = re.search(r'[?&]format=(jpg|jpeg|png|webp)', url, re.I)
        ext = m.group(1) if m else default
    return ext
