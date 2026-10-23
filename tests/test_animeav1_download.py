from core.models import EpisodeLink, EpisodeLinks
from sources.animeav1 import AnimeAV1Source
from sources.jkanime import JkanimeSource


def test_download_uses_only_sub_mp4upload(monkeypatch, tmp_path):
    src = AnimeAV1Source()
    src.get_episode_links = lambda *a, **k: EpisodeLinks(
        stream={'SUB': [], 'DUB': []},
        download={
            'SUB': [EpisodeLink(server='1Fichier', url='https://1fichier.com/?sub'),
                    EpisodeLink(server='MP4Upload', url='https://www.mp4upload.com/subid')],
            'DUB': [EpisodeLink(server='MP4Upload', url='https://www.mp4upload.com/dubid')],
        },
    )

    used = {}

    def fake_direct(url):
        used['url'] = url
        return 'https://cdn.example/video.mp4'

    monkeypatch.setattr(src, '_mp4upload_direct', fake_direct)
    monkeypatch.setattr(src, '_remote_size', lambda *a: None)
    monkeypatch.setattr(
        JkanimeSource, '_download_curl',
        lambda self, url, path, **kw: path,
    )

    out = src.download_chapter_sync('yomi-no-tsugai', '1', str(tmp_path), '1')

    assert used['url'] == 'https://www.mp4upload.com/subid'
    assert out.endswith('001.mp4')


def test_details_cover_falls_back_to_cdn(monkeypatch):
    src = AnimeAV1Source()
    monkeypatch.setattr(src, '_fetch_serie_page', lambda slug: (
        'kit.start(app, element, {node_ids: [0], data: [{type: "data", data: '
        '{media: {id: 3933, title: "Yomi no Tsugai", poster: null, episodesCount: 2}}}]})'
    ))

    details = src.get_details_sync('yomi-no-tsugai')

    assert details.cover == 'https://cdn.animeav1.com/covers/3933.jpg'
    assert details.total_episodes == 2


def test_download_falls_back_to_pixeldrain(monkeypatch, tmp_path):
    src = AnimeAV1Source()
    src.get_episode_links = lambda *a, **k: EpisodeLinks(
        stream={'SUB': [], 'DUB': []},
        download={'SUB': [EpisodeLink(server='PDrain', url='https://pixeldrain.com/u/JvqHSxgE')]},
    )
    used = {}

    def fake_direct(server, url):
        used['server'] = server
        return 'https://cdn.example/video.mp4', 'https://pixeldrain.com/', 'https://pixeldrain.com', None

    monkeypatch.setattr(src, '_download_direct', fake_direct)
    monkeypatch.setattr(src, '_remote_size', lambda *a: None)
    monkeypatch.setattr(JkanimeSource, '_download_curl', lambda self, url, path, **kw: path)

    out = src.download_chapter_sync('yomi-no-tsugai', '1', str(tmp_path), '1')

    assert used['server'] == 'pixeldrain'
    assert out.endswith('001.mp4')


def test_download_prioritizes_mp4upload_over_pixeldrain(monkeypatch, tmp_path):
    src = AnimeAV1Source()
    src.get_episode_links = lambda *a, **k: EpisodeLinks(
        stream={'SUB': [], 'DUB': []},
        download={'SUB': [
            EpisodeLink(server='PDrain', url='https://pixeldrain.com/u/JvqHSxgE'),
            EpisodeLink(server='MP4Upload', url='https://www.mp4upload.com/subid'),
        ]},
    )
    order = []

    def fake_direct(server, url):
        order.append(server)
        if server == 'mp4upload':
            raise Exception('token muerto')
        return 'https://cdn.example/video.mp4', 'https://pixeldrain.com/', 'https://pixeldrain.com', None

    monkeypatch.setattr(src, '_download_direct', fake_direct)
    monkeypatch.setattr(src, '_remote_size', lambda *a: None)
    monkeypatch.setattr(JkanimeSource, '_download_curl', lambda self, url, path, **kw: path)

    out = src.download_chapter_sync('yomi-no-tsugai', '1', str(tmp_path), '1')

    assert order == ['mp4upload', 'mp4upload', 'pixeldrain']
    assert out.endswith('001.mp4')


def test_transferit_direct_uses_file_handle(monkeypatch):
    src = AnimeAV1Source()

    def fake_call(xh, payload):
        if payload['a'] == 'xi':
            return {'size': [123, 1, 1, 0, 0]}
        return {'f': [{'h': 'root', 't': 1}, {'h': 'fileh', 't': 0, 's': 123}]}

    monkeypatch.setattr(src, '_transferit_call', fake_call)

    url, size = src._transferit_direct('https://transfer.it/t/wG5GmW5HmDSA')

    assert size == 123
    assert 'x=wG5GmW5HmDSA' in url and 'n=fileh' in url


def test_download_falls_back_to_transferit(monkeypatch, tmp_path):
    src = AnimeAV1Source()
    src.get_episode_links = lambda *a, **k: EpisodeLinks(
        stream={'SUB': [], 'DUB': []},
        download={'SUB': [EpisodeLink(server='TransferIt', url='https://transfer.it/t/wG5GmW5HmDSA')]},
    )
    captured = {}

    def fake_direct(server, url):
        assert server == 'transfer.it'
        return ('https://cdn.example/video.mp4', 'https://transfer.it/',
                'https://transfer.it', 999)

    def fake_curl(self, url, path, **kw):
        captured.update(kw)
        return path

    monkeypatch.setattr(src, '_download_direct', fake_direct)
    monkeypatch.setattr(JkanimeSource, '_download_curl', fake_curl)

    out = src.download_chapter_sync('yomi-no-tsugai', '13', str(tmp_path), '13')

    assert captured['expected'] == 999
    assert out.endswith('013.mp4')
