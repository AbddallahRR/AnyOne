import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path
from queue import Full

from fastapi import HTTPException

from core.chapter_utils import chapter_float_key
from core.database import (
    get_series_to_check,
    mark_series_checked,
    queue_find_active,
    queue_insert,
    save_content_to_db,
    set_series_updates,
)
from core.disk_cache import chapters_cache, search_cache
from core.download_worker import download_queue
from core.models import DownloadJob
from core.settings import settings
from core.sources import get_source

from . import api_router
from .common import (
    _find_local_serie_dir,
    _local_chapters_anime,
    _local_chapters_manga,
)

logger = logging.getLogger(__name__)


def _check_series_for_new_chapters(content_ref: str) -> dict:
    try:
        source_name = None
        content_id = None
        local_dir = None

        if content_ref.startswith('local:'):
            folder_name = content_ref[6:]
            for ct, base in [('anime', settings.anime_download_dir), ('manga', settings.manga_download_dir)]:
                candidate = Path(base) / folder_name
                if candidate.is_dir():
                    local_dir = candidate
                    content_type = ct
                    info_path = candidate / 'series_info.json'
                    if info_path.exists():
                        import json
                        with open(info_path, 'r', encoding='utf-8') as f:
                            info = json.load(f)
                        source_name = info.get('source')
                        content_id = info.get('content_id')
                    break
            if not local_dir:
                return {'content_ref': content_ref, 'new_chapters': [], 'error': 'Serie no encontrada en disco'}
            if not source_name or not content_id:
                return {'content_ref': content_ref, 'new_chapters': [], 'error': 'Serie local sin fuente remota asociada'}
        else:
            source_name, content_id = content_ref.split(':', 1)
            content_type = None
            for ct, base in [('anime', settings.anime_download_dir), ('manga', settings.manga_download_dir)]:
                base_path = Path(base)
                serie_dir = _find_local_serie_dir(base_path, content_id)
                if serie_dir:
                    content_type = ct
                    local_dir = serie_dir
                    break
            if not content_type:
                return {'content_ref': content_ref, 'new_chapters': [], 'error': 'Serie no encontrada en disco'}

        src = get_source(content_type, source_name)
        if not src:
            return {'content_ref': content_ref, 'new_chapters': [], 'error': f"Fuente '{source_name}' no disponible"}

        chapters_cache.delete(f'{content_type}:{source_name}:{content_id}')
        search_cache.delete(f'{source_name}:chapters:{content_id}')
        remote_chapters = src.get_chapters_sync(content_id)

        if content_type == 'anime':
            local_list = _local_chapters_anime(local_dir)
        else:
            local_list = _local_chapters_manga(local_dir)
        local_nums = {str(ch['number']) for ch in local_list}

        local_floats = [chapter_float_key(ch['number']) for ch in local_list]
        max_local = max(local_floats) if local_floats else None

        if max_local is not None:
            new_chs = [ch for ch in remote_chapters
                       if chapter_float_key(ch.number) > max_local]
        else:
            new_chs = [ch for ch in remote_chapters
                       if ch.number not in local_nums]

        new_nums = sorted({ch.number for ch in new_chs}, key=chapter_float_key)
        remote_by_num = {ch.number: ch.id for ch in new_chs}
        new_chapter_ids = [remote_by_num[n] for n in new_nums if n in remote_by_num]

        mark_series_checked(content_ref)
        set_series_updates(content_ref, new_nums)

        queued = 0
        if new_chapter_ids:
            title = local_dir.name if local_dir else content_ref
            info_path = local_dir / 'series_info.json' if local_dir else None
            if info_path and info_path.exists():
                try:
                    with open(info_path, 'r', encoding='utf-8') as f:
                        title = json.load(f).get('title', title)
                except Exception:
                    pass
            ref = f'{source_name}:{content_id}'
            try:
                save_content_to_db(content_type, source_name, content_id, title, '')
            except Exception:
                pass
            for ch_id in new_chapter_ids:
                if queue_find_active(ref, ch_id):
                    continue
                try:
                    job_id = queue_insert(ref, content_type, title, ch_id)
                    download_queue.put(DownloadJob(
                        id=job_id,
                        content_ref=ref,
                        type=content_type,
                        title=title,
                        chapter_id=ch_id,
                    ), timeout=5)
                    queued += 1
                except Full:
                    logger.warning(f"Cola de descarga llena, no se pudo encolar {ch_id}")
                    break
                except Exception as exc:
                    logger.warning(f"Error encolando {ch_id}: {exc}")

        return {
            'content_ref': content_ref,
            'new_chapters': new_nums,
            'new_chapter_ids': new_chapter_ids,
            'total_remote': len(remote_chapters),
            'total_local': len(local_list),
            'queued': queued,
            'error': None,
        }

    except Exception as exc:
        logger.exception(f"Error comprobando actualizaciones para {content_ref}:")
        return {'content_ref': content_ref, 'new_chapters': [], 'error': str(exc)}


@api_router.post('/library/check-updates/{content_ref:path}')
async def api_check_updates(content_ref: str):
    result = await asyncio.to_thread(_check_series_for_new_chapters, content_ref)
    if result.get('error'):
        raise HTTPException(status_code=500, detail='Error interno al comprobar actualizaciones')
    return result


def _check_all_updates_core() -> dict:
    pending = get_series_to_check()
    if not pending:
        return {'checked': 0, 'results': [], 'message': 'No hay series pendientes de comprobación'}

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_check_series_for_new_chapters, s['content_ref']): s
            for s in pending
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    series_with_updates = [r for r in results if r.get('new_chapters')]
    logger.info(
        f"check-all-updates: {len(results)} series comprobadas, "
        f"{len(series_with_updates)} con capítulos nuevos"
    )
    return {
        'checked': len(results),
        'with_updates': len(series_with_updates),
        'results': results,
    }


@api_router.post('/library/check-all-updates')
async def api_check_all_updates():
    return await asyncio.to_thread(_check_all_updates_core)
