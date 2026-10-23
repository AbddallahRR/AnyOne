import logging
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from core.disk_cache import img_filter_cache
from core.settings import settings
from core.models import chapter_to_filename
from core.utils import filter_manga_images, normalize_title

from . import api_router
from .common import (
    _base_folder,
    _find_local_serie_dir,
    _require_source,
    _safe_path,
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65536
_CACHE_HEADERS = {'Cache-Control': 'public, max-age=86400'}


def _file_with_etag(path: Path, request: Request) -> Response:
    """Serve a static file, answering 304 when the client's ETag still matches."""
    stat = path.stat()
    etag = f'"{stat.st_mtime:.0f}-{stat.st_size}"'
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304)
    return FileResponse(path, headers={**_CACHE_HEADERS, 'ETag': etag})


def _chapter_video(serie_dir: Path, chapter: str) -> Path | None:
    """Locate a chapter's .mp4, trying the padded numbering the downloader uses."""
    try:
        chap_int = int(float(chapter))
        numbered = f'{chap_int:03d}'
    except (ValueError, TypeError):
        numbered = None

    candidates = [f'[!.]*_{chapter}.mp4', f'{chapter}.mp4']
    if numbered:
        candidates += [f'[!.]*_{numbered}.mp4', f'{numbered}.mp4']
    for pattern in candidates:
        files = list(serie_dir.glob(pattern))
        if files:
            return files[0]
    return None


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
        thumb_path = Path(base) / Path(filename).parent / 'thumb.webp'
        if thumb_path.exists():
            return _file_with_etag(thumb_path, request)

    safe = _safe_path(base, filename)
    if not safe:
        raise HTTPException(status_code=403)
    if not safe.exists():
        raise HTTPException(status_code=404)

    return _file_with_etag(safe, request)


@api_router.get('/play/local/{type}/{id}/{chapter}')
def api_play_local(type: str, id: str, chapter: str, request: Request):
    base = _base_folder(type)
    safe = _safe_path(base, id)
    if not safe:
        raise HTTPException(status_code=403)
    if not safe.exists():
        raise HTTPException(status_code=404)
    if type == 'anime':
        video = _chapter_video(safe, chapter)
        if not video:
            raise HTTPException(status_code=404)
        return _serve_video(str(video), request)
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


_ZILLA_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64; rv:131.0) '
                   'Gecko/20100101 Firefox/131.0'),
    'Referer': 'https://player.zilla-networks.com/',
    'Origin': 'https://player.zilla-networks.com',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}


def _rewrite_zilla_playlist(text: str) -> str:
    """Reapunta segmentos al proxy y cambia .html -> .m4s (ffmpeg rechaza .html)."""
    return re.sub(
        r'https://player\.zilla-networks\.com/segs/([^"\s]+)\.html',
        r'/api/stream/zilla/segs/\1.m4s',
        text,
    )


@api_router.get('/stream/zilla/{path:path}')
async def api_stream_zilla(path: str):
    """Proxy del player zilla-networks: su WAF exige Sec-Fetch-Site de su
    propio origen para servir los segmentos, cosa que un navegador externo
    no puede falsificar."""
    if not path.startswith(('m3u8/', 'segs/')):
        raise HTTPException(status_code=404)

    import httpx

    upstream_path = path[:-4] + '.html' if path.endswith('.m4s') else path
    client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    upstream = await client.get(
        f'https://player.zilla-networks.com/{upstream_path}',
        headers=_ZILLA_HEADERS,
    )
    if upstream.status_code != 200:
        await client.aclose()
        raise HTTPException(status_code=upstream.status_code)

    if path.startswith('m3u8/'):
        await client.aclose()
        return Response(content=_rewrite_zilla_playlist(upstream.text),
                        media_type='application/vnd.apple.mpegurl',
                        headers={'Access-Control-Allow-Origin': '*'})

    async def _body():
        try:
            yield upstream.content
        finally:
            await client.aclose()

    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'video/mp4' if 'init' in path else 'video/mp2t',
        'Cache-Control': 'public, max-age=3600',
    }
    return StreamingResponse(_body(), headers=headers)


@api_router.get('/play/remote/{content_type}/{source}/{content_id}/{chapter}')
async def api_play_remote(content_type: str, source: str, content_id: str, chapter: str):
    src = _require_source(content_type, source)

    if content_type == 'anime':
        try:
            stream_url = await src.get_stream_url(content_id, chapter)
        except Exception as exc:
            logger.exception(f'Error obteniendo stream URL para {content_id}/{chapter}: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener enlace de reproducción')
        if not stream_url:
            raise HTTPException(status_code=404, detail='Esta fuente no soporta streaming remoto')
        # Detectar si es un stream directo o un embed
        stream_type = 'embed'
        sl = stream_url.lower()
        # player.zilla-networks.com requiere proxy (WAF + X-Frame-Options)
        if 'zilla-networks.com/m3u8/' in stream_url or 'zilla-networks.com/play/' in stream_url:
            m = re.search(r'/(?:m3u8|play)/([a-f0-9]+)', stream_url)
            if m:
                stream_url = f'/api/stream/zilla/m3u8/{m.group(1)}'
                stream_type = 'direct'
        elif sl.endswith('.m3u8') or '.m3u8?' in sl or sl.endswith('.mp4') or '.mp4?' in sl:
            stream_type = 'direct'
        return JSONResponse(content={'url': stream_url, 'type': stream_type})
    else:
        try:
            images = await src.get_chapter_images(content_id, chapter)
        except Exception as exc:
            logger.exception(f'Error obteniendo imagenes para {content_id}/{chapter}: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener imagenes del capitulo')
        if not images:
            raise HTTPException(status_code=404, detail='No se encontraron imagenes para este capitulo')
        cache_key = f'{content_type}:{source}:{content_id}:{chapter}:v2'
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

    return _file_with_etag(safe, request)


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


@api_router.get('/video-duration/anime/{content_id}/{chapter}')
def video_duration(content_id: str, chapter: str, request: Request):
    serie_dir = Path(str(settings.anime_download_dir)) / normalize_title(content_id)
    if not serie_dir.exists():
        raise HTTPException(status_code=404)
    video = _chapter_video(serie_dir, chapter)
    if not video:
        raise HTTPException(status_code=404)

    duration = _probe_duration(str(video))
    if duration is not None:
        return JSONResponse(
            content={'duration': duration},
            headers={'Cache-Control': 'public, max-age=86400'},
        )
    raise HTTPException(status_code=500, detail='Error al obtener duracion del video')
