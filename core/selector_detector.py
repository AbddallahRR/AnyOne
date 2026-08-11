import logging
import re

from bs4 import BeautifulSoup, Tag

from core.html_utils import (
    ATTR_PRIORITY,
    extract_background_images,
    extract_from_srcset,
    extract_images_from_noscript,
    extract_images_from_scripts,
    normalize_image_url,
)

logger = logging.getLogger(__name__)

_CSS_CLASS_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_-]*$')


def _make_selector(tag: Tag) -> str:
    if not tag or not isinstance(tag, Tag):
        return ''
    parts = [tag.name]
    if tag.get('id'):
        cid = tag['id'].replace(':', '\\:').replace('.', '\\.').replace('#', '\\#')
        parts.append(f'#{cid}')
    for cls in tag.get('class', []):
        if _CSS_CLASS_RE.match(cls):
            parts.append(f'.{cls}')
    return ''.join(parts)


def _disambiguate(tag: Tag, scope: Tag) -> str:
    """Return a CSS selector that matches *tag* inside *scope*.

    Starts from the tag's own selector and, if it matches more than one
    element within *scope*, prepends ancestor context using the child
    combinator (``p`` → ``a > p``) until the selector is unambiguous."""
    sel = _make_selector(tag)
    if not sel:
        return ''
    try:
        if len(scope.select(sel)) <= 1:
            return sel
    except Exception:
        return sel

    current = sel
    ancestor = tag.parent
    while ancestor is not None and ancestor is not scope and \
            getattr(ancestor, 'name', None) not in ('[document]', 'html'):
        ancestor_sel = ancestor.name
        if ancestor.get('id'):
            cid = ancestor['id'].replace(':', '\\:').replace('.', '\\.').replace('#', '\\#')
            ancestor_sel += f'#{cid}'
        for cls in ancestor.get('class', []):
            if _CSS_CLASS_RE.match(cls):
                ancestor_sel += f'.{cls}'
        candidate = f'{ancestor_sel} > {current}'
        try:
            matches = scope.select(candidate)
        except Exception:
            return sel
        if len(matches) == 1 and matches[0] is tag:
            return candidate
        current = candidate
        ancestor = ancestor.parent
    return sel


def _qualify_result_selector(soup: BeautifulSoup, card: Tag) -> str:
    """Return a CSS selector that targets exactly the repeating group of *card*.

    When the card's bare selector (e.g. ``li``) also matches elements outside
    the result group (nav items, etc.), ancestor context is prepended until the
    selector no longer over-matches the document."""
    sel = _make_selector(card)
    if not sel or not isinstance(card, Tag):
        return sel

    group = 0
    parent = card.parent
    if parent is not None:
        group = len([s for s in parent.children if isinstance(s, Tag) and s.name == card.name])
    try:
        total = len(soup.select(sel))
    except Exception:
        return sel
    if group <= 1 or total <= group:
        return sel

    current = sel
    ancestor = card.parent
    while ancestor is not None and ancestor.name not in ('[document]', 'html', 'body'):
        ancestor_sel = ancestor.name
        if ancestor.get('id'):
            cid = ancestor['id'].replace(':', '\\:').replace('.', '\\.').replace('#', '\\#')
            ancestor_sel += f'#{cid}'
        for cls in ancestor.get('class', []):
            if _CSS_CLASS_RE.match(cls):
                ancestor_sel += f'.{cls}'
        candidate = f'{ancestor_sel} > {current}'
        try:
            count = len(soup.select(candidate))
        except Exception:
            return current
        if 0 < count <= group:
            current = candidate
            if count == group:
                break
        ancestor = ancestor.parent
    return current


def _score_candidate(container: Tag, depth: int = 0) -> float:
    score = 0.0
    links = container.find_all('a', href=True)
    images = container.find_all('img')
    pictures = container.find_all('picture')
    text_len = len(container.get_text(strip=True))

    if len(links) >= 1:
        score += 1.0
    if len(images) >= 1:
        score += 1.5
    if pictures:
        score += 1.0
    # Bonus: card with both link and image (typical result card)
    if links and images:
        score += 0.8
    if 20 < text_len < 500:
        score += 0.5

    # Bonus for data- attributes (common in JS-rendered items)
    data_attrs = [a for a in (container.attrs or {}) if a.startswith('data-')]
    score += len(data_attrs) * 0.3

    # Bonus for lazy-loaded images (data-src, data-lazy, etc.)
    for img in images:
        for attr in ('data-src', 'data-lazy-src', 'data-original', 'data-lazy'):
            if img.get(attr):
                score += 0.4
                break

    children = [c for c in container.children if isinstance(c, Tag)]
    score -= len(children) * 0.05
    score -= depth * 0.1

    return score


def _find_repeating_patterns(soup: BeautifulSoup) -> list[Tag]:
    candidates = []
    seen = set()

    # First pass: siblings of same tag name
    for tag in soup.find_all(['div', 'li', 'tr', 'article', 'section']):
        parent = tag.parent
        siblings = [s for s in parent.find_all(lambda t: t.name == tag.name, recursive=False)] if parent else []
        if len(siblings) >= 3:
            score = _score_candidate(tag)
            if score > 1.0:
                key = (id(parent), tag.name)
                if key not in seen:
                    seen.add(key)
                    candidates.append((score, tag))

    # Second pass: same class across different parents (grid/flex layouts)
    if len(candidates) < 3:
        class_groups: dict[str, list[Tag]] = {}
        for tag in soup.find_all(True):
            classes = tag.get('class', [])
            for cls in classes:
                if _CSS_CLASS_RE.match(cls):
                    class_groups.setdefault(cls, []).append(tag)
        for cls, tags in class_groups.items():
            if len(tags) >= 3:
                for tag in tags[:5]:  # sample up to 5
                    score = _score_candidate(tag)
                    if score > 1.0 and id(tag) not in seen:
                        seen.add(id(tag))
                        candidates.append((score, tag))

    candidates.sort(key=lambda x: -x[0])
    return [t for _, t in candidates[:10]]


def _find_elements_by_text(soup: BeautifulSoup, text: str) -> list[tuple[float, Tag]]:
    """Find elements containing *text* (case-insensitive, partial), ranked by
    relevance.  Prefers elements whose visible text matches; the ``alt`` /
    ``title`` attributes are only checked as a fallback when the text does not
    appear as visible content."""
    text_lower = text.lower().strip()
    if not text_lower:
        return []
    candidates: list[tuple[float, Tag]] = []
    seen = set()

    for node in soup.find_all(string=lambda s: text_lower in s.lower()):
        parent = node.parent
        if not isinstance(parent, Tag) or id(parent) in seen:
            continue
        seen.add(id(parent))
        full = parent.get_text(strip=True)
        score = 3.0 if full.lower() == text_lower else 2.5
        if len(full) > 200:
            score -= 0.5
        candidates.append((score, parent))

    # Check alt / title attributes — only when the text is not visible
    if not candidates:
        for attr in ('alt', 'title'):
            for tag in soup.find_all(attrs={attr: True}):
                if id(tag) in seen:
                    continue
                val = tag.get(attr, '')
                if text_lower in val.lower():
                    seen.add(id(tag))
                    candidates.append((2.8, tag))

    candidates.sort(key=lambda x: -x[0])
    return candidates[:5]


def _find_parent_card(element: Tag) -> Tag:
    """Walk up from *element* until we find a container that looks like a
    repeating card / item (has at least 2 same-tag siblings under its
    parent).  A candidate is only accepted if it contains a link, so inner
    structural divs that merely share a tag name with a sibling (e.g. two
    ``<div>`` inside a ``<figure>``) are skipped.  Falls back to the element."""
    current = element.parent
    while current is not None and getattr(current, 'name', None) not in ('[document]', 'html'):
        name = current.name
        if name in ('div', 'li', 'tr', 'article', 'section', 'a', 'td'):
            parent = current.parent
            if parent:
                # Skip if parent is an <a> wrapper — it's a link, not a structural container
                if parent.name == 'a':
                    current = parent
                    continue
                siblings = [s for s in parent.children
                            if isinstance(s, Tag) and s.name == name]
                if len(siblings) >= 2 and current.find('a', href=True):
                    return current
                # list / table containers always group items
                if name in ('li', 'tr') and parent.name in ('ul', 'ol', 'tbody', 'table'):
                    return current
        current = current.parent
    return element


def detect_selector_by_text(html: str, text: str,
                            stage: str = 'details',
                            base_url: str = '') -> dict:
    """Given HTML and a visible *text* the user sees on the page, find the
    best CSS selector(s) for the relevant elements.

    *stage* controls what we look for:

    * ``'details'`` — find the element that contains *text* (title).
    * ``'search'``  — find the card containing *text*, then deduce
      title / url / cover selectors within that card.
    * ``'chapters'`` — find the item containing *text* (chapter number),
      then deduce item / num / url selectors.
    * ``'content'``  — find an <img> whose *alt* or *src* contains *text*.
    """
    soup = BeautifulSoup(html, 'html.parser')
    result: dict = {}

    # ── details ──────────────────────────────────────────────────────────
    if stage == 'details':
        cand = _find_elements_by_text(soup, text)
        if not cand:
            return {}
        score, elem = cand[0]
        container = _find_parent_card(elem)
        # If _find_parent_card didn't find a real card (no siblings), widen search
        if container is elem:
            for tag in (elem.parent, elem.find_parent('div')):
                if tag and tag.name not in ('[document]', 'html'):
                    container = tag
                    break

        result = {
            'selector': _make_selector(elem),
            'attr': 'text',
            'confidence': score,
            'matched_text': elem.get_text(strip=True)[:200],
        }

        # Try to find a cover image — prefer one whose alt/title matches the text
        text_lower = text.lower().strip()
        for img in container.find_all('img'):
            src = img.get('src', '') or img.get('data-src', '') or ''
            if not src or any(x in src.lower() for x in ('icon', 'logo', 'avatar', 'spinner', 'blank', 'loading')):
                continue
            alt = (img.get('alt') or '').lower()
            title_attr = (img.get('title') or '').lower()
            w = int(img.get('width', 0)) if img.get('width') else 0
            h = int(img.get('height', 0)) if img.get('height') else 0
            if (text_lower in alt or text_lower in title_attr) and ((w >= 50 and h >= 50) or (w == 0 and h == 0)):
                result['cover_selector'] = _make_selector(img)
                result['cover_attr'] = 'data-src' if img.get('data-src') else 'src'
                break
        if 'cover_selector' not in result:
            # Fallback 1: any decent-sized image in the container
            for img in container.find_all('img'):
                src = img.get('src', '') or img.get('data-src', '') or ''
                if not src or any(x in src.lower() for x in ('icon', 'logo', 'avatar', 'spinner', 'blank', 'loading')):
                    continue
                w = int(img.get('width', 0)) if img.get('width') else 0
                h = int(img.get('height', 0)) if img.get('height') else 0
                if (w >= 50 and h >= 50) or (w == 0 and h == 0):
                    result['cover_selector'] = _make_selector(img)
                    result['cover_attr'] = 'data-src' if img.get('data-src') else 'src'
                    break
        if 'cover_selector' not in result:
            # Fallback 2: search whole page for an img whose alt/title matches
            for img in soup.find_all('img'):
                alt = (img.get('alt') or '').lower()
                title_attr = (img.get('title') or '').lower()
                if text_lower in alt or text_lower in title_attr:
                    result['cover_selector'] = _make_selector(img)
                    result['cover_attr'] = 'data-src' if img.get('data-src') else 'src'
                    break

        return result

    # ── search ──────────────────────────────────────────────────────────
    if stage == 'search':
        cand = _find_elements_by_text(soup, text)
        if not cand:
            return {}
        score, title_elem = cand[0]
        card = _find_parent_card(title_elem)

        # Widen the search if the card is too narrow (no links or images)
        if not card.find('a', href=True) and not card.find('img'):
            ancestor = card.parent
            while ancestor is not None and ancestor.name not in ('[document]', 'html'):
                if ancestor.find('a', href=True) or ancestor.find('img'):
                    card = ancestor
                    break
                ancestor = ancestor.parent

        # Prefer <a> that matches the title text over any link in the card
        link = None
        text_lower = text.lower().strip()
        # Check if the card itself is an <a> tag
        if card.name == 'a' and card.get('href'):
            if text_lower in card.get_text(strip=True).lower():
                link = card
            elif text_lower in (card.get('title') or '').lower():
                link = card
        if not link:
            for a_tag in card.find_all('a', href=True):
                if text_lower in a_tag.get_text(strip=True).lower():
                    link = a_tag
                    break
                if text_lower in (a_tag.get('title') or '').lower():
                    link = a_tag
                    break
        if not link:
            link = card.find('a', href=True)

        # Prefer <img> whose alt/title matches the title text
        img = None
        for img_tag in card.find_all('img'):
            alt = (img_tag.get('alt') or '').lower()
            title_attr = (img_tag.get('title') or '').lower()
            if text_lower in alt or text_lower in title_attr:
                img = img_tag
                break
        if not img:
            img = card.find('img')

        cover_attr = 'src'
        if img and img.get('data-src'):
            cover_attr = 'data-src'
        elif img and img.get('data-lazy'):
            cover_attr = 'data-lazy'

        return {
            'result_selector': _qualify_result_selector(soup, card),
            'title_selector': _disambiguate(title_elem, card),
            'title_attr': 'text',
            'url_selector': _make_selector(link) if link else '',
            'url_attr': 'href',
            'cover_selector': _make_selector(img) if img else '',
            'cover_attr': cover_attr,
            'confidence': score,
        }

    # ── chapters ────────────────────────────────────────────────────────
    if stage == 'chapters':
        cand = _find_elements_by_text(soup, text)
        if not cand:
            return {}
        score, num_elem = cand[0]
        item = _find_parent_card(num_elem)

        # Widen the search if the item has no link
        if not item.find('a', href=True):
            ancestor = item.parent
            while ancestor is not None and ancestor.name not in ('[document]', 'html'):
                if ancestor.name == 'a' and ancestor.get('href'):
                    item = ancestor
                    break
                if ancestor.find('a', href=True):
                    item = ancestor
                    break
                ancestor = ancestor.parent

        # Prefer <a> whose text matches the chapter text
        link = None
        text_lower = text.lower().strip()
        # Check if the item itself is an <a> tag
        if item.name == 'a' and item.get('href'):
            if text_lower in item.get_text(strip=True).lower():
                link = item
        if not link:
            for a_tag in item.find_all('a', href=True):
                if text_lower in a_tag.get_text(strip=True).lower():
                    link = a_tag
                    break
        if not link:
            link = item.find('a', href=True)

        return {
            'item_selector': _make_selector(item),
            'num_selector': _make_selector(num_elem),
            'num_attr': 'text',
            'url_selector': _make_selector(link) if link else '',
            'url_attr': 'href',
            'confidence': score,
        }

    # ── content ─────────────────────────────────────────────────────────
    if stage == 'content':
        text_lower = text.lower().strip()
        core_text = text_lower.split(' — ')[0].split(' | ')[0].split(' – ')[0].strip()

        result = {}
        detected_pattern = None

        # Strategy 1: Search regular <img> elements (with expanded attr checking)
        for img in soup.find_all('img'):
            alt = (img.get('alt', '') or '').lower()
            src_val = (img.get('src', '') or '').lower()
            title_attr = (img.get('title', '') or '').lower()
            # Check all priority attrs
            joined_data = ''
            for attr_name in ATTR_PRIORITY:
                val = img.get(attr_name, '') or ''
                if val:
                    joined_data += val.lower() + ' '
            if (text_lower in alt or text_lower in src_val or text_lower in title_attr or text_lower in joined_data
                    or (core_text and (core_text in alt or core_text in title_attr or core_text in joined_data))):
                # Pick best attribute
                best_attr = 'src'
                for attr_name in ATTR_PRIORITY:
                    if img.get(attr_name):
                        best_attr = attr_name
                        break
                # Try srcset for larger version
                srcset_url = extract_from_srcset(img)
                if srcset_url and srcset_url != img.get('src', ''):
                    result['srcset_url'] = srcset_url
                result.update({
                    'selector': _make_selector(img),
                    'attr': best_attr,
                    'confidence': 2.0,
                    'detected_pattern': 'regular',
                })
                detected_pattern = 'regular'
                break

        # Strategy 2: Search inside <noscript> (images hidden behind JS)
        if not result:
            noscript_imgs = extract_images_from_noscript(soup)
            for entry in noscript_imgs:
                img = entry['element']
                alt = (img.get('alt', '') or '').lower()
                if text_lower in alt or core_text in alt:
                    best_attr = 'src'
                    for attr_name in ATTR_PRIORITY:
                        if img.get(attr_name):
                            best_attr = attr_name
                            break
                    result.update({
                        'selector': _make_selector(img),
                        'attr': best_attr,
                        'confidence': 2.5,
                        'detected_pattern': 'noscript',
                    })
                    detected_pattern = 'noscript'
                    break
            # If no text match in noscript, still return the first real image found
            if not result and noscript_imgs:
                entry = noscript_imgs[0]
                img = entry['element']
                best_attr = 'src'
                for attr_name in ATTR_PRIORITY:
                    if img.get(attr_name):
                        best_attr = attr_name
                        break
                result.update({
                    'selector': _make_selector(img),
                    'attr': best_attr,
                    'confidence': 1.5,
                    'detected_pattern': 'noscript',
                })
                detected_pattern = 'noscript'

        # Strategy 2b: <picture> / <source> elements
        if not result:
            for picture in soup.find_all('picture'):
                source = picture.find('source')
                img = picture.find('img')
                if source:
                    srcset = source.get('srcset') or ''
                    if srcset:
                        # Pick the largest source from srcset
                        best_url = extract_from_srcset(source) or ''
                        if best_url:
                            norm = normalize_image_url(best_url, base_url)
                            if norm:
                                result.update({
                                    'selector': 'picture > source',
                                    'attr': 'srcset',
                                    'confidence': 2.0,
                                    'detected_pattern': 'picture',
                                })
                                detected_pattern = 'picture'
                                break
                # Fallback to the <img> inside <picture>
                if img and not result:
                    best_attr = 'src'
                    for attr_name in ATTR_PRIORITY:
                        if img.get(attr_name):
                            best_attr = attr_name
                            break
                    result.update({
                        'selector': _make_selector(img),
                        'attr': best_attr,
                        'confidence': 1.8,
                        'detected_pattern': 'picture',
                    })
                    detected_pattern = 'picture'
                    break

        # Strategy 3: Extract from JS scripts
        if not result:
            script_urls = extract_images_from_scripts(soup, base_url)
            if script_urls:
                # Return first URL as reference, mark as JS-detected
                result.update({
                    'script_urls': script_urls[:5],
                    'total_script_urls': len(script_urls),
                    'confidence': 2.0,
                    'detected_pattern': 'js_var',
                    'attr': 'src',  # JS-extracted URLs are direct
                })
                detected_pattern = 'js_var'

        # Strategy 4: CSS background-image
        if not result:
            bg_urls = extract_background_images(soup, '')
            for url in bg_urls:
                norm = normalize_image_url(url, base_url)
                if norm:
                    result.update({
                        'selector': '[style*="background-image"]',
                        'attr': 'style',
                        'confidence': 1.0,
                        'detected_pattern': 'background',
                    })
                    detected_pattern = 'background'
                    break

        # Strategy 5: Fallback — first <img> with a real URL (no text match needed)
        if not result:
            for img in soup.find_all('img'):
                for attr_name in ATTR_PRIORITY:
                    val = img.get(attr_name) or ''
                    norm = normalize_image_url(val, base_url)
                    if norm:
                        result.update({
                            'selector': _make_selector(img),
                            'attr': attr_name,
                            'confidence': 0.8,
                            'detected_pattern': 'fallback',
                        })
                        detected_pattern = 'fallback'
                        break
                if result:
                    break

        if result:
            result['detected_pattern'] = result.get('detected_pattern', detected_pattern or 'unknown')
            return result
        return {}

    return {}


def detect_search_selectors(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    suggestions = []
    seen_selectors = set()

    for card in _find_repeating_patterns(soup):
        # A search result card must link to the content
        if not card.find('a', href=True):
            continue

        sel = _qualify_result_selector(soup, card)
        if not sel or sel in seen_selectors:
            continue
        seen_selectors.add(sel)

        link_el = card.find('a', href=True)
        img_el = card.find('img')

        title_sel = ''
        title_attr = 'text'
        if link_el:
            # Prefer a clean text container (p / h1-h4 / span) inside the link,
            # so cards that wrap a <figure> with metadata don't use the whole
            # link text as the title. The longest text is usually the title.
            best = None
            best_len = -1
            for candidate in card.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'span']):
                text = candidate.get_text(strip=True)
                if text and len(text) > best_len:
                    best = candidate
                    best_len = len(text)
            if best is not None:
                title_sel = _disambiguate(best, card)
            if not title_sel:
                title_sel = _disambiguate(link_el, card)
        elif img_el and img_el.get('alt'):
            title_sel = _make_selector(img_el)
            title_attr = 'alt'

        if not title_sel:
            for candidate in card.find_all(['h1', 'h2', 'h3', 'h4', 'span', 'a']):
                if candidate.get_text(strip=True):
                    title_sel = _disambiguate(candidate, card)
                    break

        url_sel = _make_selector(link_el) if link_el else ''
        url_attr = 'href'

        cover_sel = _make_selector(img_el) if img_el else ''
        cover_attr = 'src'
        if img_el and img_el.get('data-src'):
            cover_attr = 'data-src'
        elif img_el and img_el.get('data-lazy'):
            cover_attr = 'data-lazy'

        if title_sel:
            suggestions.append({
                'result_selector': sel,
                'title_selector': title_sel,
                'title_attr': title_attr,
                'url_selector': url_sel,
                'url_attr': url_attr,
                'cover_selector': cover_sel,
                'cover_attr': cover_attr,
                'confidence': round(_score_candidate(card), 2),
            })

    return suggestions[:3]


def detect_by_url_pattern(html: str, url_pattern: str, base_url: str) -> list[dict]:
    """Detect CSS selectors by finding elements whose image src/attributes
    match a given URL pattern (substring match).

    Useful when the user provides a known image URL from the page instead of
    visible text.

    Returns a list of candidates sorted by confidence.
    """
    soup = BeautifulSoup(html, 'html.parser')
    pattern_lower = url_pattern.lower()
    results: list[dict] = []
    seen_selectors: set[str] = set()

    def _check_img(img: Tag) -> dict | None:
        for attr_name in ATTR_PRIORITY:
            val = img.get(attr_name, '') or ''
            if pattern_lower in val.lower():
                sel = _make_selector(img)
                if sel and sel not in seen_selectors:
                    seen_selectors.add(sel)
                    return {
                        'selector': sel,
                        'attr': attr_name,
                        'confidence': 2.5,
                        'detected_pattern': 'url_pattern',
                    }
        # Check srcset
        srcset = img.get('srcset', '') or img.get('data-srcset', '') or ''
        if pattern_lower in srcset.lower():
            sel = _make_selector(img)
            if sel and sel not in seen_selectors:
                seen_selectors.add(sel)
                return {
                    'selector': sel,
                    'attr': 'srcset',
                    'confidence': 2.0,
                    'detected_pattern': 'url_pattern',
                }
        return None

    # Strategy 1: Direct <img> match
    for img in soup.find_all('img'):
        r = _check_img(img)
        if r:
            results.append(r)

    # Strategy 2: <noscript> images
    if not results:
        for entry in extract_images_from_noscript(soup):
            r = _check_img(entry['element'])
            if r:
                r['confidence'] = 2.0
                r['detected_pattern'] = 'noscript_url'
                results.append(r)

    # Strategy 3: <source> inside <picture>
    if not results:
        for source in soup.find_all('source'):
            srcset = source.get('srcset', '') or ''
            if pattern_lower in srcset.lower():
                parent = source.parent
                if parent and parent.name == 'picture':
                    sel = 'picture > source'
                    if sel not in seen_selectors:
                        seen_selectors.add(sel)
                        results.append({
                            'selector': sel,
                            'attr': 'srcset',
                            'confidence': 2.0,
                            'detected_pattern': 'picture_url',
                        })

    # Strategy 4: CSS background-image
    if not results:
        for el in soup.find_all(True):
            style = el.get('style', '') or ''
            if pattern_lower in style.lower():
                sel = _make_selector(el)
                if sel and sel not in seen_selectors:
                    seen_selectors.add(sel)
                    results.append({
                        'selector': sel,
                        'attr': 'style',
                        'confidence': 1.5,
                        'detected_pattern': 'background_url',
                    })

    return results[:5]
