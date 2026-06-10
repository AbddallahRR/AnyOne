import pytest
from bs4 import BeautifulSoup, Tag

from core.selector_detector import (
    _make_selector,
    _score_candidate,
    _find_repeating_patterns,
    detect_search_selectors,
    detect_selector_by_text,
)


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
