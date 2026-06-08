import logging

from fastapi import HTTPException, Request

from core.database import get_source_settings, update_source_settings
from core.sources import get_all_sources_meta

from . import api_router

logger = logging.getLogger(__name__)


@api_router.get('/settings/sources')
async def api_get_source_settings():
    settings = get_source_settings()
    meta = get_all_sources_meta()
    return [
        {
            'name': s['name'],
            'type': s['type'],
            'label': s['label'],
            'enabled': settings.get(s['name'], True),
        }
        for s in meta
    ]


@api_router.put('/settings/sources')
async def api_update_source_settings(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail='Se espera un objeto {name: bool, ...}')

    meta = get_all_sources_meta()
    valid_names = {s['name'] for s in meta}
    unknown = set(body.keys()) - valid_names
    if unknown:
        raise HTTPException(status_code=400, detail=f'Fuentes desconocidas: {", ".join(unknown)}')

    update_source_settings(body)
    logger.info(f'Configuración de fuentes actualizada: {body}')
    return {'status': 'ok'}
