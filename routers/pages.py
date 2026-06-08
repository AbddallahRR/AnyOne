import json
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=['pages'])
templates = Jinja2Templates(directory='templates')

_manifest_path = Path(__file__).resolve().parent.parent / 'static' / 'dist' / 'build.json'


def _load_bundles() -> dict:
    try:
        manifest = json.loads(_manifest_path.read_text())
        bundles = {}
        for key, filename in manifest.get('bundles', {}).items():
            bundles[key.replace(':', '_')] = f"dist/{filename}"
        return bundles
    except Exception:
        return {}


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, 'index.html', {'bundles': _load_bundles()})


@router.get('/settings', response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse(request, 'settings.html', {'bundles': _load_bundles()})


@router.get('/serie/{type}/{source}/{id}', response_class=HTMLResponse)
def serie_detail(request: Request, type: str, source: str, id: str):
    return templates.TemplateResponse(request, 'serie.html', {
        'bundles': _load_bundles(),
        'type': type, 'source': source, 'id': id
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
