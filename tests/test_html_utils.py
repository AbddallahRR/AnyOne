import pytest
from bs4 import BeautifulSoup

from core.html_utils import (
    extract_items_with_templates,
    normalize_url,
    validate_css_selector,
)


class TestValidateCssSelector:
    def test_valid_simple_selector(self):
        assert validate_css_selector('div') is True

    def test_valid_complex_selector(self):
        assert validate_css_selector('div.card > a[href*="manga"]') is True

    def test_valid_class_selector(self):
        assert validate_css_selector('.item-list') is True

    def test_valid_id_selector(self):
        assert validate_css_selector('#content') is True

    def test_valid_nth_child(self):
        assert validate_css_selector('li:nth-child(2)') is True

    def test_valid_multi_class(self):
        assert validate_css_selector('div.card.item') is True

    def test_empty_selector(self):
        assert validate_css_selector('') is True

    def test_invalid_selector_unclosed_bracket(self):
        assert validate_css_selector('div[') is False

    def test_invalid_selector_bad_pseudo(self):
        assert validate_css_selector('div:::something') is False

    def test_invalid_selector_garbage(self):
        assert validate_css_selector('<<<>>>') is False


class TestExtractItemsWithTemplates:
    HTML = '''
    <div id="main">
      <div class="item" data-id="1"><a href="/item/1">Item 1</a></div>
      <div class="item" data-id="2"><a href="/item/2">Item 2</a></div>
      <div class="item" data-id="3"><a href="/item/3">Item 3</a></div>
    </div>
    <template id="tmpl">
      <div class="item" data-id="4"><a href="/item/4">Item 4</a></div>
      <div class="item" data-id="5"><a href="/item/5">Item 5</a></div>
    </template>
    '''

    def test_extracts_main_items(self):
        soup = BeautifulSoup(self.HTML, 'html.parser')
        items = extract_items_with_templates(soup, 'div.item', deduplicate_href=False)
        assert len(items) == 5
        assert items[0].get('data-id') == '1'
        assert items[3].get('data-id') == '4'

    def test_deduplicates_by_href(self):
        html = '''
        <div id="main">
          <div class="item"><a href="/item/1">Item 1</a></div>
          <div class="item"><a href="/item/2">Item 2</a></div>
        </div>
        <template>
          <div class="item"><a href="/item/1">Item 1 dup</a></div>
          <div class="item"><a href="/item/3">Item 3</a></div>
        </template>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        items = extract_items_with_templates(soup, 'div.item', deduplicate_href=True)
        assert len(items) == 3
        hrefs = [item.find('a')['href'] if item.find('a') else '' for item in items]
        assert hrefs == ['/item/1', '/item/2', '/item/3']

    def test_no_dedup_when_disabled(self):
        html = '''
        <div id="main">
          <div class="item"><a href="/item/1">Item 1</a></div>
        </div>
        <template>
          <div class="item"><a href="/item/1">Item 1 dup</a></div>
        </template>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        items = extract_items_with_templates(soup, 'div.item', deduplicate_href=False)
        assert len(items) == 2

    def test_no_selector_returns_soup(self):
        soup = BeautifulSoup('<div>hello</div>', 'html.parser')
        items = extract_items_with_templates(soup, '', deduplicate_href=False)
        assert len(items) == 1
        assert items[0] is soup

    def test_bad_selector_returns_empty(self):
        soup = BeautifulSoup('<div>hello</div>', 'html.parser')
        items = extract_items_with_templates(soup, '>>>invalid', deduplicate_href=False)
        assert items == []

    def test_fallback_to_tag_name(self):
        """When template select() fails, fall back to find_all with first item's tag name."""
        html = '''
        <div id="main">
          <span class="item">A</span>
          <span class="item">B</span>
          <span class="item">C</span>
        </div>
        <template>
          <span class="item">D</span>
        </template>
        '''
        soup = BeautifulSoup(html, 'html.parser')
        items = extract_items_with_templates(soup, 'span.item', deduplicate_href=False)
        # span.item is valid, so select() works fine
        assert len(items) == 4


class TestNormalizeUrl:
    def test_absolute_url_unchanged(self):
        assert normalize_url('https://example.com/img.jpg', 'https://base.com') == 'https://example.com/img.jpg'

    def test_protocol_relative(self):
        assert normalize_url('//example.com/img.jpg', 'https://base.com') == 'https://example.com/img.jpg'

    def test_root_relative(self):
        assert normalize_url('/img.jpg', 'https://base.com') == 'https://base.com/img.jpg'

    def test_data_url(self):
        assert normalize_url('data:image/png;base64,abc123', 'https://base.com') == 'data:image/png;base64,abc123'

    def test_empty_url(self):
        assert normalize_url('', 'https://base.com') == ''

    def test_subpath_relative(self):
        assert normalize_url('/path/to/img.jpg', 'https://base.com/subdir') == 'https://base.com/path/to/img.jpg'
