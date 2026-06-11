import logging
import re
from pathlib import Path

from fastapi import HTTPException

from core.database import (
    clear_series_updates,
    delete_watched_chapter,
    delete_watched_chapters_batch,
    get_all_series_statuses,
    get_conn,
    get_content_ref,
    get_progress,
    get_series_status,
    get_series_with_updates,
    get_watched_chapters,
    is_chapter_watched,
    mark_chapter_as_watched,
    save_progress,
    set_series_status,
)
from core.models import (
    AcknowledgeUpdatesRequest,
    DeleteChapterRequest,
    DeleteWatchedRequest,
    ProgressRequest,
    StatusUpdateRequest,
    WatchedToggleRequest,
    parse_chapter_from_filename,
)
from core.download_worker import is_downloading
from core.utils import scan_downloaded_series

from . import api_router
from .common import (
    _base_folder,
    _delete_chapter_files,
    _require_local,
    _resolve_series_title,
)

logger = logging.getLogger(__name__)


@api_router.get('/library')
def api_library():
    return scan_downloaded_series()


@api_router.get('/library/status')
def api_library_statuses():
    return get_all_series_statuses()


@api_router.get('/library/status/{content_ref:path}')
def api_get_series_status(content_ref: str):
    return {'content_ref': content_ref, 'status': get_series_status(content_ref)}


@api_router.post('/library/status')
def api_set_series_status(data: StatusUpdateRequest):
    set_series_status(data.content_ref, data.status)
    return {'status': data.status}


@api_router.get('/progress/local/{type}/{id}')
def api_get_local_progress(type: str, id: str):
    ref = f"local:{id}"
    chapter, progress = get_progress(ref)
    return {'chapter': chapter, 'progress': progress}


@api_router.post('/progress/local/{type}/{id}')
def api_set_local_progress(type: str, id: str, data: ProgressRequest):
    ref = f"local:{id}"
    save_progress(ref, data.chapter, data.progress)
    return {'status': 'ok'}


@api_router.get('/progress/{content_type}/{source}/{content_id}')
def api_get_progress(content_type: str, source: str, content_id: str):
    ref = get_content_ref(source, content_id)
    chapter, progress = get_progress(ref)
    return {'chapter': chapter, 'progress': progress}


@api_router.post('/progress/{content_type}/{source}/{content_id}')
def api_set_progress(content_type: str, source: str, content_id: str, data: ProgressRequest):
    ref = get_content_ref(source, content_id)
    save_progress(ref, data.chapter, data.progress)
    return {'status': 'ok'}


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
                            remaining.append(m.group(1).replace('_', '.'))
                remaining.sort(key=lambda x: float(x) if x.replace('.', '', 1).isdigit() else 0)
            new_last = str(max(remaining, key=lambda x: float(x) if x.replace('.', '', 1).isdigit() else 0)) if remaining else '1'
            save_progress(data.content_ref, new_last, '0')
    except Exception as exc:
        logger.warning(f"No se pudo actualizar progreso tras eliminar capítulo {data.chapter}: {exc}")

    return {'status': 'deleted', 'chapter': data.chapter}


@api_router.get('/library/updates')
def api_library_updates():
    series = get_series_with_updates()
    if not series:
        return {'total': 0, 'series': []}

    refs = [s['content_ref'] for s in series]
    conn = get_conn()
    placeholders = ','.join('?' * len(refs))
    rows = conn.execute(
        f"SELECT id, title FROM content WHERE id IN ({placeholders})", refs
    ).fetchall()
    title_map = {r[0]: r[1] for r in rows}

    results = []
    for s in series:
        ref = s['content_ref']
        title = title_map.get(ref)
        if not title:
            parts = ref.split(':', 1)
            if len(parts) == 2:
                title = _resolve_series_title(parts[0], parts[1])
            else:
                title = ref
        results.append({
            'content_ref': ref,
            'title': title,
            'new_chapters': s['new_chapters'],
        })
    return {
        'total': len(results),
        'series': results,
    }


@api_router.post('/library/acknowledge-updates')
def api_acknowledge_updates(data: AcknowledgeUpdatesRequest):
    refs = data.content_refs or ([data.content_ref] if data.content_ref else [])
    if not refs:
        raise HTTPException(status_code=400, detail='Falta content_ref o content_refs')
    for ref in refs:
        clear_series_updates(ref)
    return {'cleared': len(refs)}
