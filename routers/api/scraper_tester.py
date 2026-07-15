import html as _html
import logging
from urllib.parse import urljoin, urlparse, urlunparse, unquote

from bs4 import BeautifulSoup
from fastapi import HTTPException, Request

from core.html_utils import (
    ATTR_PRIORITY,
    extract_background_images,
    extract_images_from_noscript,
    extract_images_from_scripts,
    extract_items_with_templates,
    normalize_image_url,
    normalize_url,
)
from core.http_pool import HTTP_TIMEOUT, HttpPool
from core.models import ReEnableRequest, ScraperConfigSchema
from core.scraper_config import get_config
from core.scraper_health import get_all_status
from core.scraper_health import re_enable as health_re_enable
from core.throttle import rate_limiter

from . import api_router

logger = logging.getLogger(__name__)


def _normalize_url(url: str, base_url: str) -> str:
    return normalize_url(url, base_url)


def _fetch_url(url: str, timeout: int = HTTP_TIMEOUT) -> str:
    rate_limiter.wait(url)
    scraper = HttpPool.get_scraper()
    resp = scraper.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _fill_template(template: str, **kwargs) -> str:
    """Safe template string replacement — avoids str.format() conflicts
    with curly braces in URLs/CSS selectors."""
    for key, value in kwargs.items():
        template = template.replace(f'{{{key}}}', str(value))
    # Collapse double slashes in the path portion of URLs
    if template.startswith('http://') or template.startswith('https://'):
        parsed = urlparse(template)
        clean_path = parsed.path.replace('//', '/')
        if clean_path != parsed.path:
            template = urlunparse((parsed.scheme, parsed.netloc, clean_path, parsed.params, parsed.query, parsed.fragment))
    return template


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
        url = _fill_template(url_template, base=base_url, query=query, page='1')
        try:
            html = _fetch_url(url)
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
            cards = extract_items_with_templates(soup, result_sel, deduplicate_href=True) if result_sel else [soup]
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
            total_cards = len(extract_items_with_templates(soup, result_sel, deduplicate_href=False)) if result_sel else 0
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

        url = _fill_template(url_template, base=base_url, content_id=content_id, page='1')
        try:
            html = _fetch_url(url)
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
                items_before = len(extract_items_with_templates(soup, item_sel, deduplicate_href=False)) if item_sel else 1
                items = extract_items_with_templates(soup, item_sel, deduplicate_href=True) if item_sel else [soup]
                if item_sel:
                    tmpl_count = len(items) - items_before
                    if tmpl_count > 0:
                        extracted.setdefault('warning', '')
                        extracted['warning'] += f' Se incluyeron {tmpl_count} capítulos ocultos dentro de un &lt;template&gt; (carga dinámica). '
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
                    # Fallback: the item itself may be the link element
                    if 'url' not in ch and item.name == 'a' and item.get('href'):
                        ch['url'] = item.get('href', '')
                elif item.name == 'a':
                    ch['url'] = item.get('href', '')
                if ch:
                    href = ch.get('url', '')
                    ch['id'] = href.rstrip('/').split('/')[-1] if href else ch.get('number', '')
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
            html = _fetch_url(url)
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
            methods_tried = []
            detected_pattern = None
            suggested_attr = img_attr

            # Strategy 1: CSS selector + configured attribute
            if img_sel:
                try:
                    imgs = soup.select(img_sel)
                except Exception:
                    imgs = []
                for img in imgs:
                    src = img.get(img_attr) or img.get('src')
                    if src:
                        norm = _normalize_url(src, base_url)
                        if norm:
                            images.append(norm)
                methods_tried.append({
                    'method': 'css_selector',
                    'attr': img_attr,
                    'count': len(images),
                })
                if images:
                    detected_pattern = 'regular'

            # Strategy 2: CSS selector + try all priority attrs
            if not images and img_sel:
                for attr_name in ATTR_PRIORITY:
                    if attr_name == img_attr:
                        continue
                    batch = []
                    try:
                        imgs = soup.select(img_sel)
                    except Exception:
                        imgs = []
                    for img in imgs:
                        src = img.get(attr_name) or img.get('src')
                        if src:
                            norm = _normalize_url(src, base_url)
                            if norm and norm not in images:
                                batch.append(norm)
                    if batch:
                        images = batch
                        suggested_attr = attr_name
                        detected_pattern = 'data-src' if attr_name.startswith('data-') else attr_name
                        methods_tried.append({
                            'method': 'css_selector_all_attrs',
                            'attr': attr_name,
                            'count': len(images),
                        })
                        break

            # Strategy 3: <noscript> extraction
            if not images:
                noscript_imgs = extract_images_from_noscript(soup)
                for entry in noscript_imgs:
                    src = entry['src']
                    norm = _normalize_url(src, base_url)
                    if norm:
                        images.append(norm)
                if images:
                    detected_pattern = 'noscript'
                    suggested_attr = list(entry['attrs'].keys())[0] if noscript_imgs and entry['attrs'] else 'src'
                methods_tried.append({
                    'method': 'noscript',
                    'count': len(images),
                })

            # Strategy 4: JS script extraction
            if not images:
                script_urls = extract_images_from_scripts(soup, base_url)
                for u in script_urls:
                    norm = _normalize_url(u, base_url)
                    if norm:
                        images.append(norm)
                if images:
                    detected_pattern = 'js_var'
                methods_tried.append({
                    'method': 'js_scripts',
                    'count': len(images),
                })

            # Strategy 5: CSS background-image
            if not images:
                bg_urls = extract_background_images(soup, img_sel)
                for u in bg_urls:
                    norm = _normalize_url(u, base_url)
                    if norm:
                        images.append(norm)
                if images:
                    detected_pattern = 'background'
                methods_tried.append({
                    'method': 'background_image',
                    'count': len(images),
                })

            extracted['images'] = images[:50]
            extracted['methods_tried'] = methods_tried
            extracted['detected_pattern'] = detected_pattern or 'none'
            if suggested_attr != img_attr:
                extracted['suggested_attr'] = suggested_attr
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


@api_router.post('/scraper-configs/check-url')
async def api_check_url(request: Request):
    """Check if a URL is reachable via HEAD request."""
    body = await request.json()
    url = body.get('url', '').strip()
    if not url:
        raise HTTPException(status_code=400, detail='URL es requerida')
    try:
        scraper = HttpPool.get_scraper()
        resp = scraper.head(
            url,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10,
            allow_redirects=True,
        )
        return {'reachable': resp.status_code < 500, 'status': resp.status_code}
    except Exception:
        return {'reachable': False, 'status': 0}


@api_router.post('/scraper-configs/auto-detect')
async def api_auto_detect(request: Request):
    body = await request.json()
    url = body.get('url', '').strip()
    stage = body.get('stage', 'search')

    if not url:
        raise HTTPException(status_code=400, detail='url is required')

    try:
        html = _fetch_url(url)
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
    """Detect CSS selectors by finding elements that contain a given text
    or match a URL pattern.

    Accepts:
    ```json
    {
      "url": "https://example.com/search?q=one+piece",
      "stage": "details|search|chapters|content",
      "text": "One Piece",                    // sample text visible on page
      "url_pattern": "cdn.example.com/img",   // OR: partial image URL to match
      "base_url": "https://example.com"       // optional, for cover URL normalization
    }
    ```
    """
    body = await request.json()
    url = body.get('url', '').strip()
    stage = body.get('stage', 'details')
    text = body.get('text', '').strip()
    url_pattern = body.get('url_pattern', '').strip()
    base_url = body.get('base_url', '').rstrip('/')

    if not url:
        raise HTTPException(status_code=400, detail='url is required')
    if not text and not url_pattern:
        raise HTTPException(status_code=400, detail='text or url_pattern is required')
    # Safety net: replace any leftover template variables (e.g. {page})
    # so detection still works even if the frontend forgot to fill them.
    url = _fill_template(url, page='1', content_id='', chapter_id='')
    # URL-decode the path — %2F in particular breaks path-based routing
    parsed = urlparse(url)
    url = urlunparse((parsed.scheme, parsed.netloc, unquote(parsed.path), parsed.params, parsed.query, parsed.fragment))

    try:
        html = _fetch_url(url)
    except Exception as exc:
        logger.exception(f'Fetch error en detect_selector: {exc}')
        raise HTTPException(status_code=502, detail='Error al obtener la pagina para deteccion de selector')

    if url_pattern:
        from core.selector_detector import detect_by_url_pattern
        results = detect_by_url_pattern(html, url_pattern, base_url)
        if not results:
            return {'detected': {}, 'warning': f'No se encontraron elementos con URL que contenga "{url_pattern}".'}
        return {'detected': results[0], 'all_results': results}

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
    sample_content_id = body.get('sample_content_id', '').strip()

    if not base_url:
        raise HTTPException(status_code=400, detail='base_url is required')
    if not search_url_template:
        raise HTTPException(status_code=400, detail='search_url_template is required')
    if not search_query:
        raise HTTPException(status_code=400, detail='search_query is required')

    from core.selector_detector import detect_search_selectors, detect_selector_by_text

    config = {}
    errors = []

    search_url = _fill_template(search_url_template, base=base_url, query=search_query, page='1')
    try:
        html = _fetch_url(search_url)
        suggestions = detect_search_selectors(html, base_url)
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

    # Try to detect details/chapters/content if sample_content_id is provided
    if sample_content_id and config.get('search_url_selector'):
        for stage in ('details', 'chapters'):
            stage_url_template = body.get(f'{stage}_url_template', '').strip()
            if not stage_url_template:
                continue
            stage_url = _fill_template(stage_url_template, base=base_url, content_id=sample_content_id)
            try:
                html = _fetch_url(stage_url)
                if stage == 'details':
                    result = detect_search_selectors(html, base_url)
                    # Just detect title and cover on the page
                    soup = BeautifulSoup(html, 'html.parser')
                    for field, text_hint in [('title', body.get('sample_title', '')), ('cover', '')]:
                        if text_hint:
                            detected = detect_selector_by_text(html, text_hint, 'details', base_url)
                            if detected:
                                config[f'details_{field}_selector'] = detected.get('selector', '')
                else:
                    detected = detect_selector_by_text(html, body.get('sample_chapter_num', '1'), 'chapters', base_url)
                    if detected:
                        config['chapters_url_template'] = stage_url_template
                        if 'item_selector' in detected:
                            config['chapters_item_selector'] = detected['item_selector']
                        if 'num_selector' in detected:
                            config['chapters_num_selector'] = detected['num_selector']
                        if 'url_selector' in detected:
                            config['chapters_url_selector'] = detected['url_selector']
            except Exception as exc:
                errors.append(f'Error fetching {stage} URL: {exc}')

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
async def api_scraper_re_enable(data: ReEnableRequest):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='name is required')
    health_re_enable(name)
    from core.database import update_source_settings
    update_source_settings({name: True})
    return {'status': 'ok', 'name': name}
