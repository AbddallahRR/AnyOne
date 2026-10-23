from routers.api.media import _rewrite_zilla_playlist


def test_playlist_segments_go_through_proxy():
    playlist = (
        '#EXTM3U\n'
        '#EXT-X-MAP:URI="https://player.zilla-networks.com/segs/abc/init.html"\n'
        '#EXTINF:10.0,\n'
        'https://player.zilla-networks.com/segs/abc/000.html\n'
    )
    out = _rewrite_zilla_playlist(playlist)
    assert '/api/stream/zilla/segs/abc/init.m4s' in out
    assert '/api/stream/zilla/segs/abc/000.m4s' in out
    assert 'player.zilla-networks.com' not in out
