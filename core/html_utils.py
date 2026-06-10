import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


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
        soup_copy = BeautifulSoup(str(soup), 'html.parser')
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
