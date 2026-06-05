from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=['pages'])
templates = Jinja2Templates(directory='templates')


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, 'index.html')


@router.get('/serie/{type}/{source}/{id}', response_class=HTMLResponse)
def serie_detail(request: Request, type: str, source: str, id: str):
    return templates.TemplateResponse(request, 'serie.html', {
        'type': type, 'source': source, 'id': id
    })


@router.get('/reader/{type}/{source}/{content_id}/{chapter}', response_class=HTMLResponse)
def reader(request: Request, type: str, source: str, content_id: str, chapter: str):
    return templates.TemplateResponse(request, 'reader.html', {
        'type': type,
        'source': source,
        'content_id': content_id,
        'chapter': chapter,
    })
