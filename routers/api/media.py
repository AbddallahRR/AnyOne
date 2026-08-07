import json
import logging
import os
import subprocess
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from core.database import save_content_to_db
from core.disk_cache import img_filter_cache
from core.settings import settings
from core.models import chapter_to_filename
from core.sources import get_source
from core.utils import filter_manga_images, normalize_title

from . import api_router
from .common import (
    _base_folder,
    _find_local_serie_dir,
    _local_chapters_anime,
    _local_chapters_manga,
    _safe_path,
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65536


def _serve_video(filepath: str, request: Request) -> Response:
    file_size = os.path.getsize(filepath)
    stat = os.stat(filepath)
    etag = f'"{stat.st_mtime:.0f}-{stat.st_size}"'

    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers={
            'Cache-Control': 'public, max-age=86400',
            'ETag': etag,
        })

    range_header = request.headers.get('range')
    if range_header:
        range_spec = range_header.strip().lower()
        if range_spec.startswith('bytes='):
            range_spec = range_spec[6:]
        parts = range_spec.split('-', 1)
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            return Response(status_code=416, headers={
                'Content-Range': f'bytes */{file_size}',
            })
        content_length = end - start + 1

        def range_gen():
            with open(filepath, 'rb') as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            range_gen(),
            status_code=206,
            media_type='video/mp4',
            headers={
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Accept-Ranges': 'bytes',
                'Content-Length': str(content_length),
                'Cache-Control': 'public, max-age=86400',
                'ETag': etag,
            },
        )

    def full_gen():
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    return FileResponse(
        filepath,
        media_type='video/mp4',
        headers={
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'public, max-age=86400',
            'ETag': etag,
        },
    )


@api_router.get('/local-cover/{type}/{filename:path}')
def local_cover(type: str, filename: str, request: Request, thumb: bool = False):
    base = _base_folder(type)
    if thumb:
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
def api_play_local(type: str, id: str, chapter: str, request: Request):
    base = _base_folder(type)
    safe = _safe_path(base, id)
    if not safe:
        raise HTTPException(status_code=403)
    if not safe.exists():
        raise HTTPException(status_code=404)
    if type == 'anime':
        files = list(safe.glob(f"[!.]*_{chapter}.mp4"))
        if not files:
            try:
                chap_int = int(float(chapter))
                files = list(safe.glob(f"[!.]*_{chap_int:03d}.mp4"))
            except (ValueError, TypeError):
                pass
        if not files:
            files = list(safe.glob(f"{chapter}.mp4"))
        if not files:
            try:
                chap_int = int(float(chapter))
                files = list(safe.glob(f"{chap_int:03d}.mp4"))
            except (ValueError, TypeError):
                pass
        if not files:
            raise HTTPException(status_code=404)
        return _serve_video(str(files[0]), request)
    else:
        cap_dir = safe / f"cap_{chapter}"
        if not cap_dir.exists():
            cap_dir = safe / f"cap_{chapter_to_filename(chapter)}"
        if not cap_dir.exists():
            try:
                cap_int = int(float(chapter))
                cap_dir = safe / f"cap_{cap_int:04d}"
            except (ValueError, TypeError):
                pass
        if not cap_dir.exists():
            raise HTTPException(status_code=404)
        images = (
            sorted(cap_dir.glob("*.jpg"))
            + sorted(cap_dir.glob("*.png"))
            + sorted(cap_dir.glob("*.webp"))
        )
        return [str(img.relative_to(str(settings.manga_download_dir))) for img in images]


@api_router.get('/play/{content_type}/{source}/{content_id}/{chapter}')
def api_play(content_type: str, source: str, content_id: str, chapter: str, request: Request):
    if content_type != 'anime':
        return {'message': 'Usa el visor de manga en el frontend'}

    serie_dir = _find_local_serie_dir(Path(str(settings.anime_download_dir)), content_id)
    if not serie_dir:
        raise HTTPException(status_code=404, detail='Archivo no encontrado')

    filepath = serie_dir / f"{serie_dir.name}_{chapter}.mp4"
    if not filepath.exists():
        try:
            chap_int = int(float(chapter))
            filepath = serie_dir / f"{serie_dir.name}_{chap_int:03d}.mp4"
        except (ValueError, TypeError):
            pass
    if not filepath or not filepath.exists():
        raise HTTPException(status_code=404, detail='Archivo no encontrado')
    return _serve_video(str(filepath), request)


@api_router.get('/play/remote/{content_type}/{source}/{content_id}/{chapter}')
async def api_play_remote(content_type: str, source: str, content_id: str, chapter: str):
    src = get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    if content_type == 'anime':
        try:
            stream_url = await src.get_stream_url(content_id, chapter)
        except Exception as exc:
            logger.exception(f'Error obteniendo stream URL para {content_id}/{chapter}: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener enlace de reproducción')
        if not stream_url:
            raise HTTPException(status_code=404, detail='Esta fuente no soporta streaming remoto')
        return JSONResponse(content={'url': stream_url, 'type': 'embed'})
    else:
        try:
            images = await src.get_chapter_images(content_id, chapter)
        except Exception as exc:
            logger.exception(f'Error obteniendo imagenes para {content_id}/{chapter}: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener imagenes del capitulo')
        if not images:
            raise HTTPException(status_code=404, detail='No se encontraron imagenes para este capitulo')
        cache_key = f'{content_type}:{source}:{content_id}:{chapter}'
        cached = await img_filter_cache.aget(cache_key)
        if cached is not None:
            return JSONResponse(content=cached)
        # Filter out small images (logos, ads, thumbnails) that cause jumps
        images = filter_manga_images(images, min_dimension=300)
        await img_filter_cache.aset(cache_key, images)
        return JSONResponse(content=images)


@api_router.get('/manga/images/{subpath:path}')
def api_manga_images(subpath: str, request: Request):
    safe = _safe_path(str(settings.manga_download_dir), subpath)
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


@lru_cache(maxsize=256)
def _probe_duration(filepath: str) -> float | None:
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filepath],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as exc:
        logger.exception(f"Error obteniendo duración: {exc}")
    return None


def _get_cached_duration(filepath: str) -> float | None:
    return _probe_duration(filepath)


@api_router.get('/video-duration/anime/{content_id}/{chapter}')
def video_duration(content_id: str, chapter: str, request: Request):
    serie_dir = Path(str(settings.anime_download_dir)) / normalize_title(content_id)
    if not serie_dir.exists():
        raise HTTPException(status_code=404)
    files = list(serie_dir.glob(f"[!.]*_{chapter}.mp4"))
    if not files:
        try:
            chap_int = int(chapter)
            files = list(serie_dir.glob(f"[!.]*_{chap_int:03d}.mp4"))
        except (ValueError, TypeError):
            pass
    if not files:
        files = list(serie_dir.glob(f"{chapter}.mp4"))
    if not files:
        try:
            chap_int = int(chapter)
            files = list(serie_dir.glob(f"{chap_int:03d}.mp4"))
        except (ValueError, TypeError):
            pass
    if not files:
        raise HTTPException(status_code=404)

    duration = _get_cached_duration(str(files[0]))
    if duration is not None:
        return JSONResponse(
            content={'duration': duration},
            headers={'Cache-Control': 'public, max-age=86400'},
        )
    raise HTTPException(status_code=500, detail='Error al obtener duracion del video')
