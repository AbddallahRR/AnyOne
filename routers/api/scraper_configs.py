import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from fastapi import HTTPException, Request

from core.http_pool import HttpPool
from core.scraper_config import (
    create_config,
    delete_config,
    get_all_configs,
    get_config,
    update_config,
)
from core.scraper_health import get_all_status
from core.scraper_health import re_enable as health_re_enable
from core.throttle import rate_limiter

from . import api_router

logger = logging.getLogger(__name__)


def _normalize_url(url: str, base_url: str) -> str:
    if not url or url.startswith('data:'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return urljoin(base_url.rstrip('/') + '/', url.lstrip('/'))
    return url


def _fill_template(template: str, **kwargs) -> str:
    """Safe template string replacement — avoids str.format() conflicts
    with curly braces in URLs/CSS selectors."""
    for key, value in kwargs.items():
        template = template.replace(f'{{{key}}}', str(value))
    return template

_TIMEOUT = 30


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
async def api_create_config(request: Request):
    body = await request.json()
    name = body.get('name', '').strip().lower().replace(' ', '-')
    if not name:
        raise HTTPException(status_code=400, detail='Name is required')
    if not re.match(r'^[a-z][a-z0-9_-]+$', name):
        raise HTTPException(
            status_code=400,
            detail='Name must start with a letter and contain only lowercase letters, numbers, hyphens, and underscores'
        )
    if get_config(name):
        raise HTTPException(status_code=409, detail='A config with this name already exists')

    source_type = body.get('type', '').strip()
    label = body.get('label', '').strip()
    base_url = body.get('base_url', '').strip()
    config = body.get('config', {})

    if not source_type or source_type not in ('anime', 'manga'):
        raise HTTPException(status_code=400, detail='Type must be "anime" or "manga"')
    if not label:
        raise HTTPException(status_code=400, detail='Label is required')
    if not base_url:
        raise HTTPException(status_code=400, detail='Base URL is required')

    try:
        result = create_config(name, source_type, label, base_url, config)
        return result
    except Exception as exc:
        logger.exception(f'Error creando configuracion {name}: {exc}')
        raise HTTPException(status_code=500, detail='Error al crear la configuracion')


@api_router.put('/scraper-configs/{name}')
async def api_update_config(name: str, request: Request):
    existing = get_config(name)
    if not existing:
        raise HTTPException(status_code=404, detail='Config not found')

    body = await request.json()
    label = body.get('label', '').strip() or None
    base_url = body.get('base_url', '').strip() or None
    enabled = body.get('enabled')
    if enabled is not None:
        enabled = bool(enabled)
    config = body.get('config')

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


@api_router.post('/scraper-configs/test')
async def api_test_config(request: Request):
    """
    Test a scraper config against a live URL.
    Accepts partial config + query, returns HTML preview or extracted data.
    """
    body = await request.json()
    config = body.get('config', {})
    query = body.get('query', '')
    base_url = body.get('base_url', '').rstrip('/')
    stage = body.get('stage', 'search')

    if not base_url:
        raise HTTPException(status_code=400, detail='base_url is required')

    if stage == 'search':
        url_template = config.get('search_url_template', '')
        if not url_template:
            raise HTTPException(status_code=400, detail='search_url_template is required')
        url = _fill_template(url_template, base=base_url, query=query)
        try:
            rate_limiter.wait(url)
            scraper = HttpPool.get_scraper()
            resp = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.exception(f'Fetch error en test_search_selectors: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener la pagina de busqueda')

        soup = BeautifulSoup(html, 'html.parser')
        result_sel = config.get('search_result_selector', '')
        title_sel = config.get('search_title_selector', '')
        title_attr = config.get('search_title_attr', 'text')
        url_sel = config.get('search_url_selector', '')
        cover_sel = config.get('search_cover_selector', '')
        cover_attr = config.get('search_cover_attr', 'src')

        extracted = []
        try:
            cards = soup.select(result_sel) if result_sel else [soup]
            if result_sel:
                for tmpl in soup.find_all('template'):
                    found = tmpl.select(result_sel)
                    if not found and cards:
                        found = tmpl.find_all(cards[0].name)
                    cards.extend(found)
        except Exception:
            cards = [soup]
        for card in cards:
            item = {}
            if title_sel:
                try:
                    elem = card.select_one(title_sel)
                except Exception:
                    elem = None
                if elem:
                    item['title'] = elem.get_text(strip=True) if title_attr == 'text' else elem.get(title_attr, '')
            if url_sel:
                try:
                    elem = card.select_one(url_sel)
                except Exception:
                    elem = None
                if elem:
                    item['url'] = elem.get('href', '')
            if not item.get('url') and card.name == 'a':
                item['url'] = card.get('href', '')
            if cover_sel:
                try:
                    elem = card.select_one(cover_sel)
                except Exception:
                    elem = None
                if elem:
                    val = elem.get(cover_attr, '')
                    item['cover'] = _normalize_url(val, base_url)
            if item:
                extracted.append(item)

        try:
            total_cards = len(soup.select(result_sel)) if result_sel else 0
            if result_sel:
                for tmpl in soup.find_all('template'):
                    found = tmpl.select(result_sel)
                    if not found:
                        main = soup.select(result_sel)
                        if main:
                            found = tmpl.find_all(main[0].name)
                    total_cards += len(found)
        except Exception:
            total_cards = 0

        warning = None
        if result_sel and total_cards <= 1:
            warning = f'El selector "{result_sel}" solo encontró {total_cards} resultado(s). Asegúrate de que apunte a cada tarjeta individual, no al contenedor.'

        result = {
            'url': url,
            'html_preview': html[:5000],
            'extracted': extracted[:20],
            'total_cards': total_cards,
        }
        if warning:
            result['warning'] = warning
        return result

    elif stage in ('details', 'chapters'):
        url_template = config.get(f'{stage}_url_template', '')
        content_id = body.get('content_id', '')
        if not url_template:
            raise HTTPException(status_code=400, detail=f'{stage}_url_template is required')
        if not content_id:
            raise HTTPException(status_code=400, detail='content_id is required')

        url = _fill_template(url_template, base=base_url, content_id=content_id)
        try:
            rate_limiter.wait(url)
            scraper = HttpPool.get_scraper()
            resp = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.exception(f'Fetch error en test_details_selectors: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener la pagina de detalles')

        soup = BeautifulSoup(html, 'html.parser')
        extracted = {'html_preview': html[:5000], 'url': url}

        if stage == 'details':
            for field in ['title', 'cover', 'synopsis']:
                sel = config.get(f'details_{field}_selector', '')
                attr = config.get(f'details_{field}_attr', 'text')
                if sel:
                    try:
                        elem = soup.select_one(sel)
                    except Exception:
                        elem = None
                    if elem:
                        val = elem.get_text(strip=True) if attr == 'text' else elem.get(attr, '')
                        if field == 'cover':
                            val = _normalize_url(val, base_url)
                        extracted[field] = val
        else:
            item_sel = config.get('chapters_item_selector', '')
            num_sel = config.get('chapters_num_selector', '')
            num_attr = config.get('chapters_num_attr', 'text')
            url_sel = config.get('chapters_url_selector', '')
            url_attr = config.get('chapters_url_attr', 'href')

            chapters = []
            try:
                items = soup.select(item_sel) if item_sel else [soup]
                if item_sel:
                    tmpl_items = []
                    for tmpl in soup.find_all('template'):
                        found = tmpl.select(item_sel)
                        if not found and items:
                            found = tmpl.find_all(items[0].name)
                        tmpl_items.extend(found)
                    if tmpl_items:
                        seen_hrefs = set()
                        for item in items:
                            href = item.get('href', '') if hasattr(item, 'get') else ''
                            seen_hrefs.add(href)
                        for item in tmpl_items:
                            href = item.get('href', '') if hasattr(item, 'get') else ''
                            if href not in seen_hrefs:
                                items.append(item)
                                seen_hrefs.add(href)
                        extracted.setdefault('warning', '')
                        extracted['warning'] += f' Se incluyeron {len(tmpl_items)} capítulos ocultos dentro de un &lt;template&gt; (carga dinámica). '
            except Exception:
                items = [soup]
            if item_sel and len(items) <= 1:
                extracted.setdefault('warning', '')
                extracted['warning'] += f'El selector "{item_sel}" solo encontró {len(items)} elemento(s). Asegúrate de que apunte a cada capítulo individual, no al contenedor.'
            for item in items:
                ch = {}
                if num_sel:
                    elem = item.select_one(num_sel)
                    if elem:
                        ch['number'] = elem.get_text(strip=True) if num_attr == 'text' else elem.get(num_attr, '')
                if url_sel:
                    elem = item.select_one(url_sel)
                    if elem:
                        ch['url'] = elem.get(url_attr, '')
                elif item.name == 'a':
                    ch['url'] = item.get('href', '')
                if ch:
                    chapters.append(ch)
            extracted['chapters'] = chapters[:50]

        return extracted

    elif stage == 'content':
        tmpl = config.get('content_page_template', '')
        content_id = body.get('content_id', '')
        chapter_id = body.get('chapter_id', '')
        if not tmpl:
            raise HTTPException(status_code=400, detail='content_page_template is required')
        if not content_id or not chapter_id:
            raise HTTPException(status_code=400, detail='content_id and chapter_id are required')

        url = _fill_template(tmpl, base=base_url, content_id=content_id, chapter_id=chapter_id)
        try:
            rate_limiter.wait(url)
            scraper = HttpPool.get_scraper()
            resp = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.exception(f'Fetch error en test_content_selectors: {exc}')
            raise HTTPException(status_code=502, detail='Error al obtener la pagina de contenido')

        soup = BeautifulSoup(html, 'html.parser')
        content_type = config.get('content_type', 'image')
        extracted = {'html_preview': html[:5000], 'url': url}

        if content_type == 'image':
            img_sel = config.get('content_image_selector', '')
            img_attr = config.get('content_image_attr', 'src')
            images = []
            try:
                imgs = soup.select(img_sel) if img_sel else []
            except Exception:
                imgs = []
            for img in imgs:
                src = img.get(img_attr) or img.get('src')
                if src:
                    images.append(_normalize_url(src, base_url))
            extracted['images'] = images
        else:
            vid_sel = config.get('content_video_selector', '')
            vid_attr = config.get('content_video_attr', 'src')
            if vid_sel:
                try:
                    elem = soup.select_one(vid_sel)
                except Exception:
                    elem = None
                if elem:
                    extracted['video_url'] = elem.get(vid_attr, '') or elem.get('src', '')

        return extracted

    raise HTTPException(status_code=400, detail=f'Unknown stage: {stage}')


@api_router.post('/scraper-configs/auto-detect')
async def api_auto_detect(request: Request):
    body = await request.json()
    url = body.get('url', '').strip()
    stage = body.get('stage', 'search')

    if not url:
        raise HTTPException(status_code=400, detail='url is required')

    try:
        rate_limiter.wait(url)
        scraper = HttpPool.get_scraper()
        resp = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.exception(f'Fetch error en auto_detect_selectors: {exc}')
        raise HTTPException(status_code=502, detail='Error al obtener la pagina para deteccion automatica')

    from core.selector_detector import detect_search_selectors

    if stage == 'search':
        base_url = body.get('base_url', url)
        suggestions = detect_search_selectors(html, base_url)
        return {'suggestions': suggestions, 'html_preview': html[:3000]}

    raise HTTPException(status_code=400, detail=f'Unknown stage: {stage}')


@api_router.post('/scraper-configs/detect-selectors')
async def api_detect_selectors(request: Request):
    """Detect CSS selectors by finding elements that contain a given text.

    Accepts:
    ```json
    {
      \"url\": \"https://example.com/search?q=one+piece\",
      \"stage\": \"details|search|chapters|content\",
      \"text\": \"One Piece\",                    // sample text visible on page
      \"base_url\": \"https://example.com\"       // optional, for cover URL normalization
    }
    ```
    """
    body = await request.json()
    url = body.get('url', '').strip()
    stage = body.get('stage', 'details')
    text = body.get('text', '').strip()
    base_url = body.get('base_url', '').rstrip('/')

    if not url:
        raise HTTPException(status_code=400, detail='url is required')
    if not text:
        raise HTTPException(status_code=400, detail='text (sample text) is required')

    try:
        rate_limiter.wait(url)
        scraper = HttpPool.get_scraper()
        resp = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.exception(f'Fetch error en detect_selector: {exc}')
        raise HTTPException(status_code=502, detail='Error al obtener la pagina para deteccion de selector')

    from core.selector_detector import detect_selector_by_text

    result = detect_selector_by_text(html, text, stage, base_url)
    if not result:
        return {'detected': {}, 'warning': f'No se encontró ningún elemento con el texto "{text}" en la página.'}

    return {'detected': result}


@api_router.post('/scraper-configs/auto-configure')
async def api_auto_configure(request: Request):
    body = await request.json()
    base_url = body.get('base_url', '').strip().rstrip('/')
    search_url_template = body.get('search_url_template', '').strip()
    search_query = body.get('search_query', '').strip()

    if not base_url:
        raise HTTPException(status_code=400, detail='base_url is required')
    if not search_url_template:
        raise HTTPException(status_code=400, detail='search_url_template is required')
    if not search_query:
        raise HTTPException(status_code=400, detail='search_query is required')

    from core.selector_detector import detect_search_selectors

    config = {}
    errors = []

    search_url = _fill_template(search_url_template, base=base_url, query=search_query)
    try:
        rate_limiter.wait(search_url)
        scraper = HttpPool.get_scraper()
        resp = scraper.get(search_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=_TIMEOUT)
        resp.raise_for_status()
        suggestions = detect_search_selectors(resp.text, base_url)
        if suggestions:
            best = suggestions[0]
            config['search_url_template'] = search_url_template
            config['search_result_selector'] = best['result_selector']
            config['search_title_selector'] = best['title_selector']
            config['search_title_attr'] = best['title_attr']
            config['search_url_selector'] = best['url_selector']
            config['search_url_attr'] = best['url_attr']
            config['search_cover_selector'] = best['cover_selector']
            config['search_cover_attr'] = best['cover_attr']
        else:
            errors.append('No se pudieron detectar selectores de búsqueda automáticamente')
    except Exception as exc:
        errors.append(f'Error fetching search URL: {exc}')

    return {'config': config, 'errors': errors, 'search_url': search_url}


# ---------------------------------------------------------------------------
# Scraper Health Status
# ---------------------------------------------------------------------------


@api_router.get('/scraper-health')
async def api_scraper_health():
    """Estado de salud de todas las fuentes (errores, desactivaciones temporales)."""
    sources_status = get_all_status()
    return sources_status


@api_router.post('/scraper-health/re-enable')
async def api_scraper_re_enable(request: Request):
    body = await request.json()
    name = body.get('name', '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='name is required')
    health_re_enable(name)
    from core.database import update_source_settings
    update_source_settings({name: True})
    return {'status': 'ok', 'name': name}
