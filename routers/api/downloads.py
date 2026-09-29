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
from core.utils import normalize_title

from . import api_router
from .common import _require_source

logger = logging.getLogger(__name__)


def _persist_content(data) -> str:
    """Register the content row and return its content_ref. Never fatal."""
    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")
    return get_content_ref(data.source, data.content_id)


def _enqueue(ref: str, data, chapter_id: str | None = None,
            skip_existing: bool = False, **extra) -> int | None:
    """Insert a queue row and hand the job to the workers.

    Returns the job id, or None when it was already queued and
    *skip_existing* is set.
    """
    existing = queue_find_active(ref, chapter_id)
    if existing:
        if skip_existing:
            return None
        raise HTTPException(
            status_code=409, detail=f"Ya está en cola (estado: {existing['status']})"
        )
    job_id = queue_insert(ref, data.type, data.title, chapter_id)
    try:
        download_queue.put(DownloadJob(
            id=job_id,
            content_ref=ref,
            type=data.type,
            title=data.title,
            chapter_id=chapter_id,
            **extra,
        ), timeout=5)
    except Full:
        raise HTTPException(status_code=503, detail='Cola de descarga llena, intente más tarde')
    return job_id


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
    _require_source(data.type, data.source)
    ref = _persist_content(data)

    excluded_chapters: list[str] = []
    if data.exclude_watched:
        safe_title = normalize_title(data.title)
        excluded_chapters = list(get_watched_chapters(f"local:{safe_title}"))
        if excluded_chapters:
            logger.debug(f"Excluyendo {len(excluded_chapters)} capítulos vistos para '{data.title}'")

    job_id = _enqueue(ref, data, excluded_chapters=excluded_chapters)
    return {'job_id': job_id, 'message': 'Descarga encolada'}


@api_router.post('/download/chapter')
def api_download_chapter(data: DownloadChapterRequest):
    _require_source(data.type, data.source)
    ref = _persist_content(data)

    job_id = _enqueue(ref, data, data.chapter_id)
    return {'job_id': job_id, 'message': 'Capítulo encolado para descarga'}


@api_router.post('/download/chapters')
def api_download_chapters(data: DownloadChaptersRequest):
    _require_source(data.type, data.source)
    ref = _persist_content(data)

    job_ids = [
        job_id for job_id in (
            _enqueue(ref, data, ch_id, skip_existing=True) for ch_id in data.chapter_ids
        ) if job_id is not None
    ]

    return {
        'job_ids': job_ids,
        'count': len(job_ids),
        'message': f'{len(job_ids)} de {len(data.chapter_ids)} capítulos encolados',
    }
