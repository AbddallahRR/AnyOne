import logging

from fastapi import HTTPException

from core.database import (
    clear_series_updates,
    get_all_series_statuses,
    get_conn,
    get_recent_progress,
    get_series_status,
    get_series_with_updates,
    set_series_status,
)
from core.models import (
    AcknowledgeUpdatesRequest,
    StatusUpdateRequest,
)
from core.utils import scan_downloaded_series
from core.settings import settings

from . import api_router
from .common import _resolve_series_title

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


@api_router.get('/library/recent')
def api_library_recent():
    recent = get_recent_progress(limit=10)
    if not recent:
        return []

    library = {item['id']: item for item in scan_downloaded_series()}
    result = []
    for entry in recent:
        folder = entry['content_ref'][6:]
        item = library.get(folder)
        if item:
            result.append({
                'id': folder,
                'title': item['title'],
                'cover': item['cover'],
                'type': item['type'],
                'chapter': entry['chapter'],
                'progress': entry['progress'],
            })
    return result


@api_router.post('/library/acknowledge-updates')
def api_acknowledge_updates(data: AcknowledgeUpdatesRequest):
    refs = data.content_refs or ([data.content_ref] if data.content_ref else [])
    if not refs:
        raise HTTPException(status_code=400, detail='Falta content_ref o content_refs')
    for ref in refs:
        clear_series_updates(ref)
    return {'cleared': len(refs)}
