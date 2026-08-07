import logging
import threading
import time
from pathlib import Path

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
from core.utils import count_images_in_dir, normalize_title, scan_downloaded_series
from core.settings import settings

from . import api_router
from .common import _resolve_series_title

logger = logging.getLogger(__name__)

_chapter_total_cache: dict[str, tuple[float, int]] = {}
_chapter_total_lock = threading.Lock()
_CHAPTER_TOTAL_TTL = 300.0


def _get_chapter_total(folder: str, content_type: str, chapter: str) -> int:
    cache_key = f'{folder}:{chapter}'
    now = time.time()
    with _chapter_total_lock:
        cached = _chapter_total_cache.get(cache_key)
        if cached and now - cached[0] < _CHAPTER_TOTAL_TTL:
            return cached[1]

    total = 0
    if content_type == 'manga':
        base = Path(str(settings.manga_download_dir)) / normalize_title(folder)
        for suffix in (f'cap_{chapter}', f'cap_{chapter.zfill(4)}'):
            cap_dir = base / suffix
            if cap_dir.is_dir():
                total = count_images_in_dir(str(cap_dir))
                break
    elif content_type == 'anime':
        base = Path(str(settings.anime_download_dir)) / normalize_title(folder)
        try:
            chap_int = int(float(chapter))
        except (ValueError, TypeError):
            chap_int = None
        matched_file = None
        for pattern in (f'*_{chapter}.mp4', f'{chapter}.mp4',
                        f'{chap_int:03d}.mp4') if chap_int else ():
            for f in base.glob(pattern):
                if f.is_file():
                    matched_file = f
                    break
            if matched_file:
                break
        if matched_file:
            try:
                from .media import _get_cached_duration
                dur = _get_cached_duration(str(matched_file))
                if dur is not None:
                    total = int(dur)
            except Exception:
                pass

    with _chapter_total_lock:
        _chapter_total_cache[cache_key] = (now, total)
    return total


def _build_recent(library: dict) -> list[dict]:
    recent = get_recent_progress(limit=10)
    if not recent:
        return []
    result = []
    for entry in recent:
        folder = entry['content_ref'][6:]
        item = library.get(folder)
        if item:
            total_episodes = int(item.get('last_chapter', '1') or '1')
            current_chapter = entry['chapter']
            content_type = item['type']
            chapter_total = _get_chapter_total(folder, content_type, current_chapter)
            result.append({
                'id': folder,
                'title': item['title'],
                'cover': item['cover'],
                'type': content_type,
                'chapter': current_chapter,
                'progress': entry['progress'],
                'total_episodes': total_episodes,
                'chapter_total': chapter_total,
            })
    return result


@api_router.get('/library')
def api_library():
    items = scan_downloaded_series()
    library = {item['id']: item for item in items}
    return {'items': items, 'recent': _build_recent(library)}


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
        content_type = None
        local_id = None

        if ref.startswith('local:'):
            folder = ref[6:]
            for ct in ('anime', 'manga'):
                base = Path(str(getattr(settings, f'{ct}_download_dir'))) / folder
                if base.is_dir():
                    content_type = ct
                    if not title:
                        info_path = base / 'series_info.json'
                        if info_path.exists():
                            try:
                                import json as _json
                                title = _json.loads(info_path.read_text(encoding='utf-8')).get('title', folder)
                            except Exception:
                                pass
                    break
            if not title:
                title = folder.replace('_', ' ').title()
            local_id = folder
        else:
            parts = ref.split(':', 1)
            if len(parts) == 2:
                if not title:
                    title = _resolve_series_title(parts[0], parts[1])
                for ct in ('anime', 'manga'):
                    from .common import _find_local_serie_dir
                    base_path = Path(str(getattr(settings, f'{ct}_download_dir')))
                    serie_dir = _find_local_serie_dir(base_path, parts[1])
                    if serie_dir:
                        content_type = ct
                        local_id = serie_dir.name
                        break
            if not title:
                title = ref
            if content_type is None:
                local_id = ref

        results.append({
            'content_ref': ref,
            'title': title,
            'new_chapters': s['new_chapters'],
            'content_type': content_type,
            'local_id': local_id,
        })
    return {
        'total': len(results),
        'series': results,
    }


@api_router.get('/library/recent')
def api_library_recent():
    items = scan_downloaded_series()
    library = {item['id']: item for item in items}
    return _build_recent(library)


@api_router.post('/library/acknowledge-updates')
def api_acknowledge_updates(data: AcknowledgeUpdatesRequest):
    refs = data.content_refs or ([data.content_ref] if data.content_ref else [])
    if not refs:
        raise HTTPException(status_code=400, detail='Falta content_ref o content_refs')
    for ref in refs:
        clear_series_updates(ref)
    return {'cleared': len(refs)}
