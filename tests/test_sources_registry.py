"""El registro de fuentes no debe duplicar nombres por clases importadas."""

from core.database import init_db

init_db()

from core.scraper_config import get_config  # noqa: E402
from core.sources import ALL_SOURCES_META  # noqa: E402


def test_source_names_are_unique():
    names = [meta['name'] for meta in ALL_SOURCES_META]
    assert len(names) == len(set(names)), names


def test_manhwaweb_is_reactivated():
    cfg = get_config('manhwaweb')
    assert cfg and cfg['built_in'] and cfg['enabled']
