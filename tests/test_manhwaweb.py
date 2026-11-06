"""ManhwaWeb: host actual de la API y capítulos identificados por el slug del link."""

from core.disk_cache import search_cache
from sources.manhwaweb import ManhwawebSource


def test_search_uses_current_api_and_first_page(monkeypatch):
    src = ManhwawebSource()
    seen = {}

    def fake_json(url):
        seen['url'] = url
        return {'data': []}

    monkeypatch.setattr(src, '_get_json', fake_json)
    monkeypatch.setattr(src, '_search_scrape', lambda query: [])

    assert src.search_sync('solo leveling') == []
    assert seen['url'].startswith('https://api.manhwaweb.com/manhwa/library?')
    assert 'page=0' in seen['url']


def test_chapters_use_link_slug_including_versions(monkeypatch):
    src = ManhwawebSource()
    content_id = 'zz-test-manhwaweb-chapters'
    search_cache.delete(f'manhwaweb:chapters:{content_id}')
    data = {
        'chapters': [
            {'chapter': 1, 'link': 'https://manhwaweb.com/leer/serie-1_01'},
            {'chapter': 2, 'link': None,
             'versions': [{'link': 'https://manhwaweb.com/leer/serie-2_02'}]},
        ]
    }
    monkeypatch.setattr(src, '_get_json', lambda url: data)

    chapters = src.get_chapters_sync(content_id)

    assert [c.id for c in chapters] == ['serie-1_01', 'serie-2_02']
    search_cache.delete(f'manhwaweb:chapters:{content_id}')


def test_series_cover_sends_referer_and_skips_html_403(tmp_path, monkeypatch):
    """El CDN de ManhwaWeb exige Referer; un 403 en HTML no debe guardarse como portada."""
    import core.database
    import core.download_worker as dw

    class Details:
        title = 'Serie'
        cover = 'https://img2mw.xyz/serie/cover.webp'

    class Resp:
        def __init__(self, status, ctype, body):
            self.status_code = status
            self.headers = {'content-type': ctype}
            self.content = body

    responses = [Resp(403, 'text/html', b'<html>403</html>'),
                 Resp(200, 'image/webp', b'RIFF\x00\x00\x00\x00WEBPfake')]
    headers_seen = []

    class Scraper:
        def get(self, url, headers=None, timeout=None):
            headers_seen.append(headers)
            return responses.pop(0)

    source = ManhwawebSource()
    monkeypatch.setattr(source, 'get_details_sync', lambda cid: Details())
    monkeypatch.setattr(source, 'scraper', Scraper())
    monkeypatch.setattr(core.database, 'save_content_to_db', lambda *a, **k: None)

    dw._save_series_metadata(str(tmp_path), 'Serie', 'manhwaweb', 'cid', 'manga', source)
    assert not (tmp_path / 'cover.webp').exists()
    assert headers_seen[0]['Referer'] == ManhwawebSource.BASE_URL

    dw._save_series_metadata(str(tmp_path), 'Serie', 'manhwaweb', 'cid', 'manga', source)
    assert (tmp_path / 'cover.webp').read_bytes().startswith(b'RIFF')

