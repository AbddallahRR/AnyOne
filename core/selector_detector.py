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
