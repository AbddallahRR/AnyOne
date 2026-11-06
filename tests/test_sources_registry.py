"""El registro de fuentes no debe duplicar nombres por clases importadas."""

from core.database import init_db

init_db()

from core.sources import ALL_SOURCES_META  # noqa: E402


def test_source_names_are_unique():
    names = [meta['name'] for meta in ALL_SOURCES_META]
    assert len(names) == len(set(names)), names
