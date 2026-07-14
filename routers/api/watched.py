import json
import logging
import re
import shutil
from pathlib import Path

from fastapi import HTTPException

from core.chapter_utils import chapter_float_key, normalize_chapter_number
from core.database import (
    delete_content_from_db,
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
    DeleteSeriesRequest,
    DeleteWatchedRequest,
    WatchedToggleRequest,
    parse_chapter_from_filename,
)
from core.download_worker import is_downloading
from core.settings import settings
from core.utils import _invalidate_scan_cache

from . import api_router
from .common import (
    _base_folder,
    _delete_chapter_files,
    _invalidate_series_index,
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


@api_router.post('/delete-series')
def api_delete_series(data: DeleteSeriesRequest):
    _require_local(data.content_ref)

    folder_name = data.content_ref[6:]
    base = Path(_base_folder(data.type))
    serie_path = base / folder_name
    if not serie_path.exists():
        raise HTTPException(status_code=404, detail='Carpeta de serie no encontrada')

    # Leer series_info.json para obtener source + content_id original
    source_name = None
    orig_content_id = None
    info_path = serie_path / 'series_info.json'
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding='utf-8'))
            source_name = info.get('source')
            orig_content_id = info.get('content_id')
        except Exception as exc:
            logger.debug(f"No se pudo leer series_info.json para '{data.content_ref}': {exc}")

    # Eliminar directorio completo del disco
    try:
        shutil.rmtree(serie_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Error al eliminar carpeta: {exc}')

    conn = get_conn()
    with conn:
        # user_progress
        conn.execute('DELETE FROM user_progress WHERE content_id = ?', (data.content_ref,))
        # watched_chapters
        conn.execute('DELETE FROM watched_chapters WHERE content_id = ?', (data.content_ref,))
        # series_status
        conn.execute('DELETE FROM series_status WHERE content_ref = ?', (data.content_ref,))

    # Limpiar entrada en tabla content si existe
    if source_name and orig_content_id:
        orig_ref = f"{source_name}:{orig_content_id}"
        delete_content_from_db(orig_ref)
        # También limpiar cola de descarga asociada
        conn.execute('DELETE FROM download_queue WHERE content_ref = ?', (orig_ref,))

    # Invalidar caches
    _invalidate_series_index(base)
    _invalidate_scan_cache()

    return {'status': 'deleted', 'content_ref': data.content_ref}
