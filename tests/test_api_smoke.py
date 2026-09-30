"""Smoke tests: the app must import, the router must wire up, and the endpoints
touched by the refactor must answer. No network: TestClient is used without the
context manager, so the lifespan (workers, scheduler, source warming) never runs.
"""

import pytest
from fastapi.testclient import TestClient

from core.database import init_db
from core.settings import settings


@pytest.fixture(scope='module')
def client():
    init_db()
    from app import app
    return TestClient(app)


class TestBasics:
    def test_db_is_not_the_development_one(self):
        assert settings.db_path.is_relative_to(settings.db_dir)

    def test_health(self, client):
        assert client.get('/health').json() == {'status': 'ok'}

    def test_pages_render(self, client):
        pages = (
            '/',
            '/settings',
            '/schedule',
            '/serie/manga/local/Demo',
            '/reader/manga/local/Demo/1',
        )
        for path in pages:
            r = client.get(path)
            assert r.status_code == 200, f'{path} -> {r.status_code}'


class TestReadOnlyEndpoints:
    def test_queue_status(self, client):
        body = client.get('/api/queue/status').json()
        assert set(body) == {'active', 'queue'}

    def test_api_library_recent(self, client):
        body = client.get('/api/library/recent').json()
        assert isinstance(body, list)

    def test_recent_remote_endpoint_lists_series(self, client):
        from core.database import save_content_to_db, save_progress
        save_content_to_db('anime', 'jkanime', 'zz-test-remoto', 'ZZ Test Remoto', 'http://cover/1.jpg')
        save_progress('jkanime:zz-test-remoto', '3', '0')
        try:
            body = client.get('/api/recent/remote/anime').json()
            assert any(i['content_id'] == 'zz-test-remoto' and i['chapter'] == '3' for i in body)
        finally:
            conn = __import__('core.database', fromlist=['get_conn']).get_conn()
            with conn:
                conn.execute("DELETE FROM user_progress WHERE content_id = ?", ('jkanime:zz-test-remoto',))
                conn.execute("DELETE FROM content WHERE id = ?", ('jkanime:zz-test-remoto',))

    def test_recent_remote_excludes_local(self, client):
        from core.database import get_conn, save_progress
        save_progress('local:zz-test-local', '1', '0')
        try:
            body = client.get('/api/recent/remote/anime').json()
            assert not any(i['content_id'] == 'zz-test-local' for i in body)
        finally:
            conn = get_conn()
            with conn:
                conn.execute("DELETE FROM user_progress WHERE content_id = ?", ('local:zz-test-local',))

    def test_sources_are_listed(self, client):
        body = client.get('/api/settings/sources').json()
        assert isinstance(body, list)
        assert all({'name', 'type', 'label', 'enabled'} <= set(s) for s in body)

    def test_settings_roundtrip_shape(self, client):
        assert isinstance(client.get('/api/settings').json(), dict)

    def test_openapi_builds(self, client):
        # Catches broken route signatures across every router at once.
        assert '/api/search' in client.get('/openapi.json').json()['paths']


class TestNotFoundHandling:
    def test_unknown_source_is_404(self, client):
        r = client.get('/api/search?q=naruto&source=nope&type=manga')
        assert r.status_code == 404

    def test_unknown_route_is_404(self, client):
        assert client.get('/api/definitely-not-a-route').status_code == 404


class TestChapterVideoLookup:
    def _dir_with(self, tmp_path, name):
        (tmp_path / name).write_bytes(b'x')
        return tmp_path

    def test_finds_exact_name(self, tmp_path):
        from routers.api.media import _chapter_video
        d = self._dir_with(tmp_path, 'One Piece_005.mp4')
        assert _chapter_video(d, '005').name == 'One Piece_005.mp4'

    def test_pads_numeric_chapter(self, tmp_path):
        from routers.api.media import _chapter_video
        d = self._dir_with(tmp_path, 'One Piece_005.mp4')
        assert _chapter_video(d, '5').name == 'One Piece_005.mp4'

    def test_falls_back_to_bare_number(self, tmp_path):
        from routers.api.media import _chapter_video
        d = self._dir_with(tmp_path, '005.mp4')
        assert _chapter_video(d, '5').name == '005.mp4'

    def test_returns_none_when_absent(self, tmp_path):
        from routers.api.media import _chapter_video
        assert _chapter_video(tmp_path, '5') is None

    def test_non_numeric_chapter_is_used_verbatim(self, tmp_path):
        from routers.api.media import _chapter_video
        d = self._dir_with(tmp_path, 'Serie_extra.mp4')
        assert _chapter_video(d, 'extra').name == 'Serie_extra.mp4'

    def test_skips_dotfiles(self, tmp_path):
        from routers.api.media import _chapter_video
        (tmp_path / '.hidden_005.mp4').write_bytes(b'x')
        assert _chapter_video(tmp_path, '5') is None
