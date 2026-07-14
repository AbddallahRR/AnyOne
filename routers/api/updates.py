import asyncio
import concurrent.futures
import logging
from pathlib import Path

from fastapi import HTTPException

from core.chapter_utils import chapter_float_key
from core.database import (
    get_series_to_check,
    mark_series_checked,
    set_series_updates,
)
from core.disk_cache import chapters_cache, search_cache
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
        if content_ref.startswith('local:'):
            return {'content_ref': content_ref, 'new_chapters': [], 'error': 'Serie solo local, sin fuente remota'}

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

        return {
            'content_ref': content_ref,
            'new_chapters': new_nums,
            'new_chapter_ids': new_chapter_ids,
            'total_remote': len(remote_chapters),
            'total_local': len(local_list),
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
