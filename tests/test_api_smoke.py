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

    def test_library(self, client):
        assert isinstance(client.get('/api/library').json(), dict)

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
