import logging
import re
from pathlib import Path

from fastapi import HTTPException

from core.chapter_utils import chapter_float_key, normalize_chapter_number
from core.database import (
    delete_watched_chapter,
    delete_watched_chapters_batch,
    get_conn,
    get_progress,
    get_watched_chapters,
    is_chapter_watched,
    mark_chapter_as_watched,
    save_progress,
)
from core.models import (
    DeleteChapterRequest,
    DeleteWatchedRequest,
    WatchedToggleRequest,
    parse_chapter_from_filename,
)
from core.download_worker import is_downloading

from . import api_router
from .common import (
    _base_folder,
    _delete_chapter_files,
    _require_local,
)

logger = logging.getLogger(__name__)


@api_router.post('/watched')
def api_mark_watched(data: WatchedToggleRequest):
    mark_chapter_as_watched(data.content_ref, data.chapter)
    return {'status': 'ok'}


@api_router.get('/watched/{content_ref:path}')
def api_get_watched(content_ref: str):
    return {'watched': get_watched_chapters(content_ref)}


@api_router.post('/watched/toggle')
def api_toggle_watched(data: WatchedToggleRequest):
    if is_chapter_watched(data.content_ref, data.chapter):
        delete_watched_chapter(data.content_ref, data.chapter)
        return {'status': 'unwatched'}
    mark_chapter_as_watched(data.content_ref, data.chapter)
    return {'status': 'watched'}


@api_router.post('/delete-watched')
def api_delete_watched(data: DeleteWatchedRequest):
    _require_local(data.content_ref)

    last_chapter_str, _ = get_progress(data.content_ref)

    watched = get_watched_chapters(data.content_ref)
    if not watched:
        return {'message': 'No hay capítulos vistos para borrar'}

    folder_name = data.content_ref[6:]
    serie_path = Path(_base_folder(data.type)) / folder_name
    if not serie_path.exists():
        raise HTTPException(status_code=404, detail='Carpeta no encontrada')

    deleted = []
    skipped = []
    for chap in watched:
        if chap == last_chapter_str:
            continue
        if is_downloading(str(serie_path), chap):
            skipped.append(chap)
            continue
        try:
            _delete_chapter_files(serie_path, data.type, chap)
            deleted.append(chap)
        except Exception as exc:
            logger.exception(f"Error borrando capítulo {chap} de '{data.content_ref}': {exc}")
    if deleted:
        delete_watched_chapters_batch(data.content_ref, deleted)

    msg = f'Se eliminaron {len(deleted)} capítulos vistos'
    if skipped:
        msg += f', {len(skipped)} omitidos por estar en descarga'
    return {'deleted': deleted, 'skipped': skipped, 'message': msg}


@api_router.post('/delete-chapter')
def api_delete_chapter(data: DeleteChapterRequest):
    _require_local(data.content_ref)

    folder_name = data.content_ref[6:]
    serie_path = Path(_base_folder(data.type)) / folder_name
    if not serie_path.exists():
        raise HTTPException(status_code=404, detail='Carpeta no encontrada')

    if is_downloading(str(serie_path), data.chapter):
        raise HTTPException(status_code=409, detail='Capítulo en descarga, no se puede borrar')

    try:
        _delete_chapter_files(serie_path, data.type, data.chapter)
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Error al eliminar archivo')

    last_chapter_str, _ = get_progress(data.content_ref)
    try:
        if last_chapter_str == data.chapter:
            if data.type == 'anime':
                remaining = sorted(
                    (parse_chapter_from_filename(f.stem) or '0') for f in serie_path.glob("*.mp4")
                )
            else:
                remaining = []
                for d in serie_path.iterdir():
                    if d.is_dir() and d.name.startswith('cap_'):
                        m = re.search(r'cap_([\d._]+)', d.name)
                        if m:
                            remaining.append(normalize_chapter_number(m.group(1).replace('_', '.')))
                remaining.sort(key=chapter_float_key)
            new_last = str(max(remaining, key=chapter_float_key)) if remaining else '1'
            save_progress(data.content_ref, new_last, '0')
    except Exception as exc:
        logger.warning(f"No se pudo actualizar progreso tras eliminar capítulo {data.chapter}: {exc}")

    return {'status': 'deleted', 'chapter': data.chapter}
