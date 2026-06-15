import logging
import re

from fastapi import HTTPException

from core.html_utils import validate_css_selector
from core.models import CreateScraperConfigRequest, ScraperConfigSchema, UpdateScraperConfigRequest
from core.scraper_config import (
    create_config,
    delete_config,
    get_all_configs,
    get_config,
    update_config,
)

from . import api_router

logger = logging.getLogger(__name__)


_SELECTOR_FIELDS = [
    'search_result_selector', 'search_title_selector', 'search_url_selector', 'search_cover_selector',
    'details_title_selector', 'details_cover_selector', 'details_synopsis_selector',
    'chapters_item_selector', 'chapters_num_selector', 'chapters_url_selector',
    'content_image_selector', 'content_video_selector',
    'catalog_item_selector', 'catalog_title_selector', 'catalog_url_selector', 'catalog_cover_selector',
]


def _validate_config_selectors(config: dict) -> list[str]:
    """Validate all CSS selectors in the config. Returns list of error messages."""
    errors = []
    for field in _SELECTOR_FIELDS:
        sel = config.get(field, '')
        if sel and not validate_css_selector(sel):
            errors.append(f'Invalid CSS selector for "{field}": {sel}')
    return errors


@api_router.get('/scraper-configs')
async def api_list_configs():
    return get_all_configs()


@api_router.get('/scraper-configs/{name}')
async def api_get_config(name: str):
    cfg = get_config(name)
    if not cfg:
        raise HTTPException(status_code=404, detail='Config not found')
    return cfg


@api_router.post('/scraper-configs')
async def api_create_config(data: CreateScraperConfigRequest):
    name = data.name.strip().lower().replace(' ', '-')
    if not re.match(r'^[a-z][a-z0-9_-]+$', name):
        raise HTTPException(
            status_code=400,
            detail='Name must start with a letter and contain only lowercase letters, numbers, hyphens, and underscores'
        )
    if get_config(name):
        raise HTTPException(status_code=409, detail='A config with this name already exists')

    if data.type not in ('anime', 'manga'):
        raise HTTPException(status_code=400, detail='Type must be "anime" or "manga"')
    if not data.label:
        raise HTTPException(status_code=400, detail='Label is required')
    if not data.base_url:
        raise HTTPException(status_code=400, detail='Base URL is required')

    config = data.config
    try:
        validated = ScraperConfigSchema(**config)
        config = validated.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Invalid config: {exc}')

    # Validate CSS selectors
    selector_errors = _validate_config_selectors(config)
    if selector_errors:
        raise HTTPException(status_code=400, detail='; '.join(selector_errors))

    try:
        result = create_config(name, data.type, data.label, data.base_url, config)
        return result
    except Exception as exc:
        logger.exception(f'Error creando configuracion {name}: {exc}')
        raise HTTPException(status_code=500, detail='Error al crear la configuracion')


@api_router.put('/scraper-configs/{name}')
async def api_update_config(name: str, data: UpdateScraperConfigRequest):
    existing = get_config(name)
    if not existing:
        raise HTTPException(status_code=404, detail='Config not found')

    label = data.label
    base_url = data.base_url
    enabled = data.enabled
    config = data.config

    if config is not None:
        try:
            validated = ScraperConfigSchema(**config)
            config = validated.model_dump()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f'Invalid config: {exc}')

        # Validate CSS selectors
        selector_errors = _validate_config_selectors(config)
        if selector_errors:
            raise HTTPException(status_code=400, detail='; '.join(selector_errors))

    try:
        result = update_config(name, label=label, base_url=base_url,
                               enabled=enabled, config=config)
        return result
    except Exception as exc:
        logger.exception(f'Error actualizando configuracion {name}: {exc}')
        raise HTTPException(status_code=500, detail='Error al actualizar la configuracion')


@api_router.delete('/scraper-configs/{name}')
async def api_delete_config(name: str):
    deleted = delete_config(name)
    if not deleted:
        raise HTTPException(status_code=404, detail='Config not found or is built-in')
    return {'status': 'deleted'}
