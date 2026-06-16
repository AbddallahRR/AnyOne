import json
import logging
from pathlib import Path

from fastapi import HTTPException

from core.database import save_content_to_db
from core.disk_cache import chapters_cache, details_cache
from core.sources import get_source
from core.utils import normalize_title

from . import api_router
from .common import (
    _base_folder,
    _find_local_serie_dir,
    _local_chapters_anime,
    _local_chapters_manga,
)

logger = logging.getLogger(__name__)


@api_router.get('/content/local/{type}/{id}')
def api_local_content_details(type: str, id: str):
    normalized_id = normalize_title(id)
    serie_path = Path(_base_folder(type)) / normalized_id

    cover_url = ''
    if (serie_path / 'thumb.webp').exists() and not (serie_path / 'cover.webp').exists():
        cover_url = f'/api/local-cover/{type}/{normalized_id}/thumb.webp?thumb=1'
    else:
        for ext in ['jpg', 'jpeg', 'png', 'webp']:
            if (serie_path / f'cover.{ext}').exists():
                cover_url = f'/api/local-cover/{type}/{normalized_id}/cover.{ext}'
                break

    title = id
    synopsis = 'Contenido descargado localmente.'
    info_path = serie_path / 'series_info.json'
    source_name = ''
    remote_id = ''
    if info_path.exists():
        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
            title = info.get('title', id)
            synopsis = info.get('synopsis', synopsis)
            source_name = info.get('source', '') or ''
            remote_id = info.get('content_id', '') or ''
        except Exception:
            pass

    return {
        'title': title,
        'cover': cover_url,
        'synopsis': synopsis,
        'source': source_name,
        'remote_id': remote_id,
    }


@api_router.get('/chapters/local/{type}/{id}')
def api_local_chapters(type: str, id: str):
    base_dir = Path(_base_folder(type))
    serie_dir = _find_local_serie_dir(base_dir, id)
    if not serie_dir:
        logger.debug(f"api_local_chapters: carpeta no encontrada para '{id}'")
        return []

    if type == 'anime':
        return _local_chapters_anime(serie_dir)
    return _local_chapters_manga(serie_dir)


@api_router.get('/chapters/with-local/{type}/{source}/{id}')
async def api_chapters_with_local(type: str, source: str, id: str):
    src = get_source(type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')
    try:
        remote_chapters = await src.get_chapters(id)
        base_dir = Path(_base_folder(type))
        serie_dir = _find_local_serie_dir(base_dir, id)

        local_chapters: set[str] = set()
        if serie_dir:
            local_list = (_local_chapters_anime(serie_dir) if type == 'anime'
                          else _local_chapters_manga(serie_dir))
            local_chapters = {str(ch['number']) for ch in local_list}

        result = []
        for ch in remote_chapters:
            result.append({
                'number': ch.number,
                'id': ch.id,
                'is_downloaded': ch.number in local_chapters,
            })
        return result
    except Exception:
        logger.exception("Error en api_chapters_with_local:")
        raise HTTPException(status_code=500, detail='Error al obtener capitulos')


@api_router.get('/content/{content_type}/{source}/{content_id}')
async def api_content_details(content_type: str, source: str, content_id: str, refresh: bool = False):
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    cache_key = f'{content_type}:{source}:{content_id}'
    if not refresh:
        cached = await details_cache.aget(cache_key)
        if cached is not None:
            return cached

    try:
        details = await src.get_details(content_id)
        save_content_to_db(content_type, source, content_id,
                           details.title, details.cover or '')
        result = details.model_dump()
        await details_cache.aset(cache_key, result)
        return result
    except Exception:
        logger.exception("Error en api_content_details:")
        raise HTTPException(status_code=500, detail='Error al obtener detalles')


@api_router.get('/chapters/{content_type}/{source}/{content_id}')
async def api_chapters(content_type: str, source: str, content_id: str, refresh: bool = False):
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    cache_key = f'{content_type}:{source}:{content_id}'
    if not refresh:
        cached = await chapters_cache.aget(cache_key)
        if cached is not None:
            return cached

    try:
        chapters = await src.get_chapters(content_id)
        result = [c.model_dump() for c in chapters]
        await chapters_cache.aset(cache_key, result)
        return result
    except Exception:
        logger.exception("Error en api_chapters:")
        raise HTTPException(status_code=500, detail='Error al obtener capitulos')
