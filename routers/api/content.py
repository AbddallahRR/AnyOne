import json
import logging
import subprocess
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR
from core.database import save_content_to_db
from core.sources import get_source
from core.utils import normalize_title

from . import api_router
from .common import (
    _base_folder,
    _find_local_serie_dir,
    _local_chapters_anime,
    _local_chapters_manga,
    _safe_path,
)

logger = logging.getLogger(__name__)

# ── Rutas específicas (con segmentos literales) ANTES que las genéricas ──

@api_router.get('/content/local/{type}/{id}')
def api_local_content_details(type: str, id: str):
    normalized_id = normalize_title(id)
    serie_path = Path(_base_folder(type)) / normalized_id

    cover_url = ''
    # Preferir thumbnail WebP si existe y la original no es ya WebP (animada)
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

        local_chapters: set[int] = set()
        if serie_dir:
            local_list = (_local_chapters_anime(serie_dir) if type == 'anime'
                          else _local_chapters_manga(serie_dir))
            local_chapters = {ch['number'] for ch in local_list}

        result = []
        for ch in remote_chapters:
            try:
                num = int(float(ch.number))
            except (TypeError, ValueError):
                num = None
            result.append({
                'number': ch.number,
                'id': ch.id,
                'is_downloaded': (num in local_chapters) if num is not None else False,
            })
        return result
    except Exception as exc:
        logger.exception("Error en api_chapters_with_local:")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Rutas genéricas ──

@api_router.get('/content/{content_type}/{source}/{content_id}')
async def api_content_details(content_type: str, source: str, content_id: str):
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')
    try:
        details = await src.get_details(content_id)
        save_content_to_db(content_type, source, content_id,
                           details.title, details.cover or '')
        return details.model_dump()
    except Exception as exc:
        logger.exception("Error en api_content_details:")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get('/chapters/{content_type}/{source}/{content_id}')
async def api_chapters(content_type: str, source: str, content_id: str):
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')
    try:
        chapters = await src.get_chapters(content_id)
        return [c.model_dump() for c in chapters]
    except Exception as exc:
        logger.exception("Error en api_chapters:")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get('/local-cover/{type}/{filename:path}')
def local_cover(type: str, filename: str, request: Request, thumb: bool = False):
    base = _base_folder(type)
    if thumb:
        # Intentar servir thumbnail WebP
        serie_dir = Path(base) / Path(filename).parent
        thumb_path = serie_dir / 'thumb.webp'
        if thumb_path.exists():
            stat = thumb_path.stat()
            etag = f'"{stat.st_mtime:.0f}-{stat.st_size}"'
            if etag and request.headers.get('if-none-match') == etag:
                return Response(status_code=304)
            return FileResponse(thumb_path, headers={
                'Cache-Control': 'public, max-age=86400',
                'ETag': etag,
            })

    safe = _safe_path(base, filename)
    if not safe:
        raise HTTPException(status_code=403)
    if not safe.exists():
        raise HTTPException(status_code=404)

    stat = safe.stat()
    etag = f'"{stat.st_mtime:.0f}-{stat.st_size}"'
    if etag and request.headers.get('if-none-match') == etag:
        return Response(status_code=304)

    return FileResponse(safe, headers={
        'Cache-Control': 'public, max-age=86400',
        'ETag': etag,
    })


@api_router.get('/play/local/{type}/{id}/{chapter}')
def api_play_local(type: str, id: str, chapter: str):
    base = _base_folder(type)
    safe = _safe_path(base, id)
    if not safe:
        raise HTTPException(status_code=403)
    if not safe.exists():
        raise HTTPException(status_code=404)
    if type == 'anime':
        try:
            chap_num = int(chapter)
        except ValueError:
            raise HTTPException(status_code=400)
        files = list(safe.glob(f"*_{chap_num:03d}.mp4"))
        if not files:
            raise HTTPException(status_code=404)
        return FileResponse(files[0], headers={"Accept-Ranges": "bytes"})
    else:
        try:
            cap_dir = safe / f"cap_{int(chapter):04d}"
        except ValueError:
            raise HTTPException(status_code=400)
        if not cap_dir.exists():
            raise HTTPException(status_code=404)
        images = (
            sorted(cap_dir.glob("*.jpg"))
            + sorted(cap_dir.glob("*.png"))
            + sorted(cap_dir.glob("*.webp"))
        )
        return [str(img.relative_to(MANGA_DOWNLOAD_DIR)) for img in images]


@api_router.get('/play/{content_type}/{source}/{content_id}/{chapter}')
def api_play(content_type: str, source: str, content_id: str, chapter: str):
    if content_type != 'anime':
        return {'message': 'Usa el visor de manga en el frontend'}

    try:
        chap_num = int(float(chapter)) if any(c.isdigit() for c in chapter) else 0
    except ValueError:
        raise HTTPException(status_code=400, detail='Capítulo inválido')

    serie_dir = _find_local_serie_dir(Path(ANIME_DOWNLOAD_DIR), content_id)
    if not serie_dir:
        raise HTTPException(status_code=404, detail='Archivo no encontrado')

    filepath = serie_dir / f"{serie_dir.name}_{chap_num:03d}.mp4"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail='Archivo no encontrado')
    return FileResponse(filepath, headers={"Accept-Ranges": "bytes"})


@api_router.get('/play/remote/{content_type}/{source}/{content_id}/{chapter}')
async def api_play_remote(content_type: str, source: str, content_id: str, chapter: str):
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    if content_type == 'anime':
        stream_url = await src.get_stream_url(content_id, chapter)
        if not stream_url:
            raise HTTPException(status_code=404, detail='Esta fuente no soporta streaming remoto')
        return RedirectResponse(url=stream_url, status_code=307)
    else:
        images = await src.get_chapter_images(content_id, chapter)
        if not images:
            raise HTTPException(status_code=404, detail='No se encontraron imágenes para este capítulo')
        return JSONResponse(content=images)


@api_router.get('/manga/images/{subpath:path}')
def api_manga_images(subpath: str, request: Request):
    safe = _safe_path(MANGA_DOWNLOAD_DIR, subpath)
    if not safe:
        raise HTTPException(status_code=403)
    if not safe.exists():
        raise HTTPException(status_code=404)

    stat = safe.stat()
    etag = f'"{stat.st_mtime:.0f}-{stat.st_size}"'
    if etag and request.headers.get('if-none-match') == etag:
        return Response(status_code=304)

    return FileResponse(safe, headers={
        'Cache-Control': 'public, max-age=86400',
        'ETag': etag,
    })


@api_router.get('/video-duration/anime/{content_id}/{chapter}')
def video_duration(content_id: str, chapter: str, request: Request):
    serie_dir = Path(ANIME_DOWNLOAD_DIR) / normalize_title(content_id)
    if not serie_dir.exists():
        raise HTTPException(status_code=404)
    try:
        chap_num = int(chapter)
    except ValueError:
        raise HTTPException(status_code=400)

    files = list(serie_dir.glob(f"*_{chap_num:03d}.mp4"))
    if not files:
        raise HTTPException(status_code=404)

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(files[0])],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            # Cachear duración por archivo (rara vez cambia)
            return JSONResponse(
                content={'duration': duration},
                headers={'Cache-Control': 'public, max-age=86400'},
            )
    except Exception as exc:
        logger.error(f"Error obteniendo duración: {exc}")

    raise HTTPException(status_code=500)
