import logging

from core.database import (
    get_content_ref,
    get_progress,
    save_progress,
)
from core.models import ProgressRequest

from . import api_router

logger = logging.getLogger(__name__)


@api_router.get('/progress/local/{type}/{id}')
def api_get_local_progress(type: str, id: str):
    ref = f"local:{id}"
    chapter, progress = get_progress(ref)
    return {'chapter': chapter, 'progress': progress}


@api_router.post('/progress/local/{type}/{id}')
def api_set_local_progress(type: str, id: str, data: ProgressRequest):
    ref = f"local:{id}"
    save_progress(ref, data.chapter, data.progress)
    return {'status': 'ok'}


@api_router.get('/progress/{content_type}/{source}/{content_id}')
def api_get_progress(content_type: str, source: str, content_id: str):
    ref = get_content_ref(source, content_id)
    chapter, progress = get_progress(ref)
    return {'chapter': chapter, 'progress': progress}


@api_router.post('/progress/{content_type}/{source}/{content_id}')
def api_set_progress(content_type: str, source: str, content_id: str, data: ProgressRequest):
    ref = get_content_ref(source, content_id)
    save_progress(ref, data.chapter, data.progress)
    return {'status': 'ok'}
