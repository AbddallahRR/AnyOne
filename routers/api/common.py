import logging
import shutil
from pathlib import Path

from fastapi import HTTPException

from core.library_scan import (  # noqa: F401  re-export: los routers importan desde aquí
    _build_series_index,
    _find_local_serie_dir,
    _get_series_index,
    _invalidate_series_index,
    _local_chapters_anime,
    _local_chapters_manga,
    _read_series_info,
    _resolve_series_title,
)
from core.models import chapter_to_filename
from core.settings import settings
from core.sources import get_source

logger = logging.getLogger(__name__)


def _safe_path(base: str, untrusted: str) -> Path | None:
    try:
        resolved = Path(base, untrusted).resolve()
        if resolved.is_relative_to(Path(base).resolve()):
            return resolved
    except Exception as exc:
        logger.debug("_safe_path: ruta no válida o fuera del directorio base: %s", exc)
    return None


def _base_folder(content_type: str) -> str:
    return str(settings.anime_download_dir) if content_type == 'anime' else str(settings.manga_download_dir)


def _require_local(content_ref: str):
    if not content_ref.startswith('local:'):
        raise HTTPException(status_code=400, detail='Solo funciona con contenido local')


def _require_source(content_type: str, source: str):
    """Return the source instance, or 404 if it is not registered."""
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')
    return src


def _delete_chapter_files(serie_path: Path, content_type: str, chapter: str) -> None:
    chap_str = chapter_to_filename(chapter, padding=3 if content_type == 'anime' else 4)
    if content_type == 'anime':
        for f in serie_path.glob(f"{chap_str}.mp4"):
            f.unlink()
    else:
        cap_dir = serie_path / f"cap_{chap_str}"
        if cap_dir.exists() and cap_dir.is_dir():
            shutil.rmtree(cap_dir)
