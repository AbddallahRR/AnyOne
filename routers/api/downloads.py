import logging
from queue import Full

from fastapi import HTTPException

from core.database import (
    get_content_ref,
    get_watched_chapters,
    queue_find_active,
    queue_get_status,
    queue_insert,
    save_content_to_db,
)
from core.download_progress import get as get_file_progress
from core.download_worker import download_queue
from core.models import (
    DownloadChapterRequest,
    DownloadChaptersRequest,
    DownloadJob,
    DownloadRequest,
)
from core.sources import get_source
from core.utils import normalize_title

from . import api_router

logger = logging.getLogger(__name__)


@api_router.get('/queue/status')
def api_queue_status():
    active, pending = queue_get_status()
    for job in active:
        fp = get_file_progress(job['id'])
        if fp:
            job['file_progress'] = fp
    return {'active': active, 'queue': pending}


@api_router.post('/download')
def api_download(data: DownloadRequest):
    src = get_source(data.type, data.source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")

    ref = get_content_ref(data.source, data.content_id)

    excluded_chapters: list[str] = []
    if data.exclude_watched:
        safe_title = normalize_title(data.title)
        watched = get_watched_chapters(f"local:{safe_title}")
        excluded_chapters = list(watched)
        if excluded_chapters:
            logger.debug(f"Excluyendo {len(excluded_chapters)} capítulos vistos para '{data.title}'")

    existing = queue_find_active(ref)
    if existing:
        raise HTTPException(status_code=409, detail=f"Ya está en cola (estado: {existing['status']})")

    job_id = queue_insert(ref, data.type, data.title)
    try:
        download_queue.put(DownloadJob(
            id=job_id,
            content_ref=ref,
            type=data.type,
            title=data.title,
            excluded_chapters=excluded_chapters,
        ), timeout=5)
    except Full:
        raise HTTPException(status_code=503, detail='Cola de descarga llena, intente más tarde')
    return {'job_id': job_id, 'message': 'Descarga encolada'}


@api_router.post('/download/chapter')
def api_download_chapter(data: DownloadChapterRequest):
    src = get_source(data.type, data.source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")

    ref = get_content_ref(data.source, data.content_id)

    existing = queue_find_active(ref, data.chapter_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Ya está en cola (estado: {existing['status']})")

    job_id = queue_insert(ref, data.type, data.title, data.chapter_id)
    try:
        download_queue.put(DownloadJob(
            id=job_id,
            content_ref=ref,
            type=data.type,
            title=data.title,
            chapter_id=data.chapter_id,
        ), timeout=5)
    except Full:
        raise HTTPException(status_code=503, detail='Cola de descarga llena, intente más tarde')
    return {'job_id': job_id, 'message': 'Capítulo encolado para descarga'}


@api_router.post('/download/chapters')
def api_download_chapters(data: DownloadChaptersRequest):
    src = get_source(data.type, data.source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")

    ref = get_content_ref(data.source, data.content_id)

    job_ids = []
    for ch_id in data.chapter_ids:
        existing = queue_find_active(ref, ch_id)
        if existing:
            continue
        job_id = queue_insert(ref, data.type, data.title, ch_id)
        try:
            download_queue.put(DownloadJob(
                id=job_id,
                content_ref=ref,
                type=data.type,
                title=data.title,
                chapter_id=ch_id,
            ), timeout=5)
        except Full:
            raise HTTPException(status_code=503, detail='Cola de descarga llena, intente más tarde')
        job_ids.append(job_id)

    return {
        'job_ids': job_ids,
        'count': len(job_ids),
        'message': f'{len(job_ids)} de {len(data.chapter_ids)} capítulos encolados',
    }
