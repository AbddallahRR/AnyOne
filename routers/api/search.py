import asyncio
import json
import logging

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.database import get_conn, get_content_ref
from core.disk_cache import search_cache
from core.models import SearchQuery
from core.sources import SOURCES, get_source

from . import api_router

logger = logging.getLogger(__name__)


@api_router.get('/search')
async def api_search(qs: SearchQuery = Depends()):
    if not qs.source:
        raise HTTPException(status_code=400, detail='Faltan parámetros type y source')

    cache_key = f"search:{qs.type}:{qs.source}:{qs.q}"

    if not qs.refresh:
        cached = search_cache.get(cache_key)
        if cached is not None:
            return cached

    source = get_source(qs.type, qs.source)
    if not source:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')

    try:
        results = await source.search(qs.q)

        refs = [get_content_ref(qs.source, r.id) for r in results]
        if refs:
            placeholders = ','.join('?' * len(refs))
            conn = get_conn()
            progress_map = {
                row[0]: (row[1], row[2])
                for row in conn.execute(
                    f'SELECT content_id, chapter, progress FROM user_progress '
                    f'WHERE content_id IN ({placeholders})',
                    refs
                ).fetchall()
            }
        else:
            progress_map = {}

        for r, ref in zip(results, refs):
            chapter, progress = progress_map.get(ref, ('1', '0'))
            r.last_chapter = chapter
            r.progress = progress

        search_cache.set(cache_key, [r.model_dump() for r in results])
        return [r.model_dump() for r in results]
    except Exception as exc:
        logger.exception("Error en api_search:")
        raise HTTPException(status_code=500, detail=str(exc))


@api_router.get('/search-all')
async def api_search_all(qs: SearchQuery = Depends()):
    cache_key = f"search_all:{qs.type}:{qs.q}"

    if not qs.refresh:
        cached = search_cache.get(cache_key)
        if cached is not None:
            return cached

    sources_dict = SOURCES.get(qs.type, {})
    if not sources_dict:
        raise HTTPException(status_code=400, detail='Tipo no soportado')

    async def search_in_source(source_name: str, src) -> list:
        try:
            items = await src.search(qs.q)
            for item in items:
                item.source = source_name
            return items
        except Exception as exc:
            logger.error(f"Error buscando en {source_name}: {exc}")
            return []

    tasks = [search_in_source(name, src) for name, src in sources_dict.items()]
    nested = await asyncio.gather(*tasks)
    results = [item for sublist in nested for item in sublist]

    unique = {f"{r.source}:{r.id}": r for r in results}
    results = sorted(unique.values(), key=lambda x: x.title or '')

    search_cache.set(cache_key, [r.model_dump() for r in results])
    return [r.model_dump() for r in results]


_SSE_TIMEOUT = 90


@api_router.get('/search-all-stream')
async def api_search_all_stream(qs: SearchQuery = Depends()):
    if not qs.q:
        raise HTTPException(status_code=400, detail='Faltan parámetros type y q')

    sources_dict = SOURCES.get(qs.type, {})
    if not sources_dict:
        raise HTTPException(status_code=400, detail='Tipo no soportado')

    cache_key = f"search_all_stream:{qs.type}:{qs.q}"
    cached = search_cache.get(cache_key)
    if cached is not None:
        async def _from_cache():
            for src_name, items in cached.items():
                yield f"event: results\ndata: {json.dumps({'source': src_name, 'results': items})}\n\n"
            yield "event: done\ndata: {}\n\n"
        return StreamingResponse(_from_cache(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache'})

    async def generate():
        all_results: dict[str, list] = {}

        async def search_in_source(source_name: str, src) -> tuple[str, list]:
            try:
                items = await src.search(qs.q)
                for item in items:
                    item.source = source_name
                return source_name, [m.model_dump() for m in items]
            except Exception as exc:
                logger.error(f"Error buscando en {source_name}: {exc}")
                return source_name, []

        tasks = {name: search_in_source(name, src) for name, src in sources_dict.items()}

        for name, coro in tasks.items():
            try:
                source_name, items = await asyncio.wait_for(coro, timeout=_SSE_TIMEOUT)
                all_results[source_name] = items
                yield f"event: results\ndata: {json.dumps({'source': source_name, 'results': items})}\n\n"
            except asyncio.TimeoutError:
                logger.warning(f"SSE search-all timeout para '{name}' tras {_SSE_TIMEOUT}s")
                continue
            except Exception:
                continue

        if all_results:
            search_cache.set(cache_key, all_results)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(generate(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})
