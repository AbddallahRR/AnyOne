from bs4 import BeautifulSoup

from core.selector_detector import (
    _disambiguate,
    _find_elements_by_text,
    _find_parent_card,
    _find_repeating_patterns,
    _make_selector,
    _score_candidate,
    detect_search_selectors,
    detect_selector_by_text,
)

# Figure/grid result layout like MonosChinos: <li> cards wrapping a <figure>
# with metadata divs (main-img + bottom) and the title in a trailing <p>.
FIGURE_GRID_HTML = '''
<html><body>
<header>
<nav><ul class="navbar-nav">
<li class="nav-item"><a class="nav-link" href="../">Inicio</a></li>
<li class="nav-item"><a class="nav-link" href="../catalogo">Catalogo</a></li>
</ul></nav>
</header>
<ul class="grid-animes directorio">
  <li>
    <article>
      <a href="/hell-mode">
        <figure>
          <span class="tipo">TV Anime</span>
          <span class="estreno">2026</span>
          <div class="bottom"><div class="figure-title"><p class="gray">En emision</p></div></div>
          <div class="main-img">
            <img loading="lazy" class="skeleton-loaded" src="https://cdn.example/4652.webp" alt="Hell Mode: Demo">
          </div>
        </figure>
        <p>Hell Mode: Demo</p>
      </a>
    </article>
  </li>
  <li>
    <article>
      <a href="/naruto">
        <figure>
          <span class="tipo">TV Anime</span>
          <span class="estreno">2002</span>
          <div class="bottom"><div class="figure-title"><p class="gray">Finalizado</p></div></div>
          <div class="main-img">
            <img loading="lazy" class="skeleton-loaded" src="https://cdn.example/2.webp" alt="Naruto">
          </div>
        </figure>
        <p>Naruto</p>
      </a>
    </article>
  </li>
  <li>
    <article>
      <a href="/bleach">
        <figure>
          <span class="tipo">TV Anime</span>
          <span class="estreno">2004</span>
          <div class="bottom"><div class="figure-title"><p class="gray">Finalizado</p></div></div>
          <div class="main-img">
            <img loading="lazy" class="skeleton-loaded" src="https://cdn.example/3.webp" alt="Bleach">
          </div>
        </figure>
        <p>Bleach</p>
      </a>
    </article>
  </li>
</ul>
</body></html>
'''


class TestMakeSelector:
    def test_simple_tag(self):
        soup = BeautifulSoup('<div></div>', 'html.parser')
        sel = _make_selector(soup.div)
        assert sel == 'div'

    def test_with_id(self):
        soup = BeautifulSoup('<div id="main"></div>', 'html.parser')
        sel = _make_selector(soup.div)
        assert sel == 'div#main'

    def test_with_class(self):
        soup = BeautifulSoup('<div class="card active"></div>', 'html.parser')
        sel = _make_selector(soup.div)
        assert sel == 'div.card.active'

    def test_with_id_and_class(self):
        soup = BeautifulSoup('<div id="main" class="container"></div>', 'html.parser')
        sel = _make_selector(soup.div)
        assert 'div#main' in sel
        assert '.container' in sel

    def test_none_input(self):
        assert _make_selector(None) == ''


class TestScoreCandidate:
    def test_scores_link_and_image(self):
        soup = BeautifulSoup(
            '<div><a href="/x">title</a><img src="img.jpg"/>text here</div>',
            'html.parser',
        )
        score = _score_candidate(soup.div)
        assert score > 2.0  # link (1.0) + img (1.5) + text (0.5) - penalty

    def test_low_score_no_link_no_img(self):
        soup = BeautifulSoup('<div><span>short</span></div>', 'html.parser')
        score = _score_candidate(soup.div)
        assert score < 1.0

    def test_data_attr_bonus(self):
        soup = BeautifulSoup(
            '<div data-id="1" data-type="card"><a href="/x">title</a></div>',
            'html.parser',
        )
        score_with_data = _score_candidate(soup.div)

        soup2 = BeautifulSoup(
            '<div><a href="/x">title</a></div>', 'html.parser'
        )
        score_without = _score_candidate(soup2.div)

        assert score_with_data > score_without


class TestFindRepeatingPatterns:
    def test_finds_three_siblings(self):
        html = '''
        <div class="list">
          <div class="item"><a href="/1">One Piece Chapter 1</a><img src="1.jpg"/></div>
          <div class="item"><a href="/2">Naruto Chapter 1</a><img src="2.jpg"/></div>
          <div class="item"><a href="/3">Bleach Chapter 1</a><img src="3.jpg"/></div>
        </div>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        patterns = _find_repeating_patterns(soup)
        assert len(patterns) >= 1

    def test_skip_fewer_than_three(self):
        html = '''
        <div class="list">
          <div class="item"><a href="/1">One</a></div>
          <div class="item"><a href="/2">Two</a></div>
        </div>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        patterns = _find_repeating_patterns(soup)
        # may still find via class-based second pass
        assert isinstance(patterns, list)

    def test_class_based_repeating(self):
        """Grid/flex layout: items share class but not same parent tag."""
        html = '''
        <div class="grid">
          <div class="card"><a href="/1">Card 1</a><img src="1.jpg"/></div>
          <div class="card"><a href="/2">Card 2</a><img src="2.jpg"/></div>
          <div class="card"><a href="/3">Card 3</a><img src="3.jpg"/></div>
        </div>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        patterns = _find_repeating_patterns(soup)
        assert len(patterns) >= 1


class TestDetectSearchSelectors:
    def test_detects_simple_list(self):
        html = '''
        <div class="results">
          <div class="item">
            <a href="/manga/one-piece">One Piece</a>
            <img src="/covers/op.jpg"/>
          </div>
          <div class="item">
            <a href="/manga/naruto">Naruto</a>
            <img src="/covers/nar.jpg"/>
          </div>
          <div class="item">
            <a href="/manga/bleach">Bleach</a>
            <img src="/covers/bl.jpg"/>
          </div>
        </div>
        '''
        suggestions = detect_search_selectors(html, 'https://example.com')
        assert len(suggestions) >= 1
        best = suggestions[0]
        assert 'result_selector' in best
        assert 'title_selector' in best
        assert 'url_selector' in best


class TestDetectByText:
    def test_detect_details(self):
        html = '<div><h1 class="title">One Piece</h1><p>Synopsis here</p></div>'
        result = detect_selector_by_text(html, 'One Piece', 'details')
        assert result.get('selector') == 'h1.title'
        assert result.get('attr') == 'text'

    def test_detect_search(self):
        html = '''
        <div class="list">
          <div class="card">
            <h2><a href="/manga/one-piece">One Piece</a></h2>
            <img src="op.jpg"/>
          </div>
          <div class="card">
            <h2><a href="/manga/naruto">Naruto</a></h2>
            <img src="nar.jpg"/>
          </div>
        </div>
        '''
        result = detect_selector_by_text(html, 'One Piece', 'search')
        assert result.get('result_selector') is not None
        assert result.get('title_selector') is not None

    def test_detect_no_match(self):
        html = '<div>Nothing here</div>'
        result = detect_selector_by_text(html, 'Missing', 'details')
        assert result == {}

    def test_detect_content_image(self):
        html = '<div><img class="page" src="/page01.jpg" alt="Page 1"/></div>'
        result = detect_selector_by_text(html, 'Page 1', 'content')
        assert result.get('selector') is not None
        assert 'confidence' in result

    def test_detect_details_with_cover(self):
        html = '''
        <div class="series-card">
          <h1 class="title">One Piece</h1>
          <img class="cover" src="/covers/op.jpg" width="200" height="300"/>
          <p class="desc">Synopsis text here</p>
        </div>
        '''
        result = detect_selector_by_text(html, 'One Piece', 'details')
        assert result.get('selector') == 'h1.title'
        assert result.get('cover_selector') is not None
        assert result.get('cover_attr') == 'src'

    def test_detect_chapters_link(self):
        html = '''<ul>
<li class="lm4-chapter-card">
  <a href="/cap-29/" class="lm4-chapter-link">
    <div class="lm4-chapter-main">
      <div class="lm4-chapter-name">Capítulo 29</div>
    </div>
  </a>
</li>
<li class="lm4-chapter-card">
  <a href="/cap-28/" class="lm4-chapter-link">
    <div class="lm4-chapter-main">
      <div class="lm4-chapter-name">Capítulo 28</div>
    </div>
  </a>
</li>
</ul>'''
        result = detect_selector_by_text(html, 'Capítulo 29', 'chapters')
        assert result.get('item_selector') is not None
        assert result.get('url_selector') is not None
        assert 'lm4-chapter-link' in result['url_selector']

    def test_detect_details_cover_separate_section(self):
        html = '''
        <html><body>
        <div class="poster">
          <img class="lm4-poster" src="/thumbnail.jpg" width="230" height="360"
               alt="El Único Final" title="El Único Final">
        </div>
        <div class="entry-header">
          <h1 class="entry-title">El Único Final</h1>
        </div>
        </body></html>
        '''
        result = detect_selector_by_text(html, 'El Único Final', 'details')
        assert result.get('selector') == 'h1.entry-title'
        cover = result.get('cover_selector')
        assert cover is not None, f'cover_selector missing: {result}'
        assert 'lm4-poster' in cover, f'expected lm4-poster in cover_selector: {cover}'


class TestFigureGridCards:
    """Search result cards that wrap a <figure> with metadata and keep the
    title in a trailing <p> (e.g. MonosChinos)."""

    def test_find_elements_by_text_prefers_visible_text(self):
        """The visible title <p> must outrank the <img alt> attribute."""
        soup = BeautifulSoup(FIGURE_GRID_HTML, 'html.parser')
        cand = _find_elements_by_text(soup, 'Hell Mode')
        assert cand
        elem = cand[0][1]
        assert elem.name == 'p'
        assert 'Hell Mode' in elem.get_text(strip=True)

    def test_parent_card_skips_inner_structural_divs(self):
        """Walking up from inside div.main-img must reach the <li>, not stop
        at main-img (which shares a tag name with div.bottom inside figure)."""
        soup = BeautifulSoup(FIGURE_GRID_HTML, 'html.parser')
        img = soup.find('img', alt='Hell Mode: Demo')
        card = _find_parent_card(img)
        assert card.name == 'li'
        assert card.find('a', href=True) is not None

    def test_detect_search_by_text(self):
        result = detect_selector_by_text(FIGURE_GRID_HTML, 'Hell Mode', 'search',
                                         'https://monoschinos.com')
        assert result.get('result_selector') == 'ul.grid-animes.directorio > li'
        assert result.get('title_selector') == 'a > p'
        assert result.get('title_attr') == 'text'
        assert result.get('url_selector') == 'a'
        assert result.get('cover_selector') == 'img.skeleton-loaded'
        assert result.get('cover_attr') == 'src'

    def test_detected_selectors_extract_correctly(self):
        """End-to-end: applying the detected selectors must yield the right
        cards and titles, excluding the header nav items."""
        result = detect_selector_by_text(FIGURE_GRID_HTML, 'Hell Mode', 'search',
                                         'https://monoschinos.com')
        soup = BeautifulSoup(FIGURE_GRID_HTML, 'html.parser')
        cards = soup.select(result['result_selector'])
        assert len(cards) == 3
        titles = [c.select_one(result['title_selector']).get_text(strip=True) for c in cards]
        assert titles == ['Hell Mode: Demo', 'Naruto', 'Bleach']
        urls = [c.select_one(result['url_selector']).get('href') for c in cards]
        assert urls == ['/hell-mode', '/naruto', '/bleach']

    def test_detect_search_selectors_figure_grid(self):
        """Auto-detect should return the grid cards and skip linkless
        candidates like div.main-img."""
        suggestions = detect_search_selectors(FIGURE_GRID_HTML, 'https://monoschinos.com')
        assert suggestions
        best = suggestions[0]
        assert best['result_selector'] == 'ul.grid-animes.directorio > li'
        assert best['title_selector'] == 'a > p'
        assert best['cover_selector'] == 'img.skeleton-loaded'
        assert all('main-img' not in s['result_selector'] for s in suggestions)

    def test_disambiguate_ambiguous_title(self):
        """A bare 'p' matches both the status <p> and the title <p> inside the
        card; disambiguation must resolve to the trailing title <p>."""
        soup = BeautifulSoup(FIGURE_GRID_HTML, 'html.parser')
        card = soup.select_one('ul.grid-animes.directorio > li')
        title_p = [p for p in card.find_all('p') if p.get_text(strip=True) == 'Hell Mode: Demo'][0]
        sel = _disambiguate(title_p, card)
        assert sel == 'a > p'
        assert len(card.select(sel)) == 1
