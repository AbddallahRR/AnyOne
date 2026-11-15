"""La nav activa (sidebar escritorio y bottom-nav móvil) sigue al ?tab= de la URL."""

import pytest
from fastapi.testclient import TestClient

from core.database import init_db


@pytest.fixture(scope='module')
def client():
    init_db()
    from app import app
    return TestClient(app)


def test_default_tab_is_library(client):
    html = client.get('/').text
    assert 'href="/?tab=library" class="bn-item active"' in html
    assert 'id="tab-library" href="/?tab=library" class="sidebar-item active"' in html


@pytest.mark.parametrize('tab', ['anime', 'manga'])
def test_tab_highlights_both_navs(client, tab):
    html = client.get(f'/?tab={tab}').text
    assert f'href="/?tab={tab}" class="bn-item active"' in html
    assert f'id="tab-{tab}" href="/?tab={tab}" class="sidebar-item active"' in html
    assert 'href="/?tab=library" class="bn-item"' in html
