import logging
import re

from bs4 import BeautifulSoup, Tag

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


def _score_candidate(container: Tag, depth: int = 0) -> float:
    score = 0.0
    links = container.find_all('a', href=True)
    images = container.find_all('img')
    text_len = len(container.get_text(strip=True))

    if len(links) >= 1:
        score += 1.0
    if len(images) >= 1:
        score += 1.5
    if 20 < text_len < 500:
        score += 0.5

    children = [c for c in container.children if isinstance(c, Tag)]
    score -= len(children) * 0.05
    score -= depth * 0.1

    return score


def _find_repeating_patterns(soup: BeautifulSoup) -> list[Tag]:
    candidates = []
    for tag in soup.find_all(['div', 'li', 'tr', 'article', 'section']):
        parent = tag.parent
        siblings = [s for s in parent.find_all(lambda t: t.name == tag.name, recursive=False)] if parent else []
        if len(siblings) >= 3:
            score = _score_candidate(tag)
            if score > 1.0:
                candidates.append((score, tag))
    candidates.sort(key=lambda x: -x[0])
    return [t for _, t in candidates[:10]]


def _find_elements_by_text(soup: BeautifulSoup, text: str) -> list[tuple[float, Tag]]:
    """Find elements containing *text* (case-insensitive, partial), ranked by
    relevance.  Checks both visible text and common attributes (alt, title)."""
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
        score = 3.0 if full.lower() == text_lower else 2.0
        if len(full) > 200:
            score -= 0.5
        candidates.append((score, parent))

    # Check alt / title attributes
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
    parent).  Falls back to the element itself."""
    current = element.parent
    while current is not None and getattr(current, 'name', None) not in ('[document]', 'html'):
        name = current.name
        if name in ('div', 'li', 'tr', 'article', 'section', 'a', 'td'):
            parent = current.parent
            if parent:
                siblings = [s for s in parent.children
                            if isinstance(s, Tag) and s.name == name]
                if len(siblings) >= 2:
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
        return {
            'selector': _make_selector(elem),
            'attr': 'text',
            'confidence': score,
            'matched_text': elem.get_text(strip=True)[:200],
        }

    # ── search ──────────────────────────────────────────────────────────
    if stage == 'search':
        cand = _find_elements_by_text(soup, text)
        if not cand:
            return {}
        score, title_elem = cand[0]
        card = _find_parent_card(title_elem)

        link = card.find('a', href=True)
        img = card.find('img')
        cover_attr = 'src'
        if img and img.get('data-src'):
            cover_attr = 'data-src'
        elif img and img.get('data-lazy'):
            cover_attr = 'data-lazy'

        return {
            'result_selector': _make_selector(card),
            'title_selector': _make_selector(title_elem),
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
        for img in soup.find_all('img'):
            alt = img.get('alt', '')
            src = img.get('src', '')
            data_src = img.get('data-src') or img.get('data-lazy') or img.get('data-original') or ''
            if text.lower() in alt.lower() or text.lower() in src.lower() or text.lower() in data_src.lower():
                attr = 'src'
                if data_src and (not src or any(c in (img.get('class') or []) for c in ('page-img-lazy', 'lazy', 'lozad'))):
                    attr = 'data-src'
                elif not src and data_src:
                    attr = 'data-src'
                return {
                    'selector': _make_selector(img),
                    'attr': attr,
                    'confidence': 2.0,
                }
        return {}

    return {}


def detect_search_selectors(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    suggestions = []
    seen_selectors = set()

    for card in _find_repeating_patterns(soup):
        sel = _make_selector(card)
        if not sel or sel in seen_selectors:
            continue
        seen_selectors.add(sel)

        link_el = card.find('a', href=True)
        img_el = card.find('img')

        title_sel = ''
        title_attr = 'text'
        if link_el:
            title_sel = _make_selector(link_el)
            if not link_el.get_text(strip=True):
                parent = link_el.find_parent(['div', 'h1', 'h2', 'h3', 'h4', 'span'])
                if parent:
                    title_sel = _make_selector(parent)
        elif img_el and img_el.get('alt'):
            title_sel = _make_selector(img_el)
            title_attr = 'alt'

        if not title_sel:
            for candidate in card.find_all(['h1', 'h2', 'h3', 'h4', 'span', 'a']):
                if candidate.get_text(strip=True):
                    title_sel = _make_selector(candidate)
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
