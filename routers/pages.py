import json
import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.sources import get_source

router = APIRouter(tags=['pages'])
templates = Jinja2Templates(directory='templates')

_manifest_path = Path(__file__).resolve().parent.parent / 'static' / 'dist' / 'build.json'
_manifest_cache: dict | None = None


def _load_bundles() -> dict:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    try:
        manifest = json.loads(_manifest_path.read_text())
        bundles = {}
        for key, filename in manifest.get('bundles', {}).items():
            bundles[key.replace(':', '_')] = f"dist/{filename}"
        _manifest_cache = bundles
        return bundles
    except Exception as exc:
        logging.warning('pages: error cargando manifest.json: %s', exc)
        _manifest_cache = {}
        return {}


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, 'index.html', {'bundles': _load_bundles()})


@router.get('/settings', response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse(request, 'settings.html', {'bundles': _load_bundles()})


@router.get('/serie/{type}/{source}/{id}', response_class=HTMLResponse)
def serie_detail(request: Request, type: str, source: str, id: str):
    can_stream = False
    if source != 'local':
        src = get_source(type, source)
        if src is not None:
            can_stream = type == 'manga' or src.supports_streaming

    return templates.TemplateResponse(request, 'serie.html', {
        'bundles': _load_bundles(),
        'type': type, 'source': source, 'id': id,
        'can_stream': can_stream,
    })


@router.get('/reader/{type}/{source}/{content_id}/{chapter}', response_class=HTMLResponse)
def reader(request: Request, type: str, source: str, content_id: str, chapter: str):
    return templates.TemplateResponse(request, 'reader.html', {
        'bundles': _load_bundles(),
        'type': type,
        'source': source,
        'content_id': content_id,
        'chapter': chapter,
    })
