#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import concurrent.futures
import json
import logging

from flask import jsonify, request, Response

from ..api import api_bp
from core.database import get_content_ref, get_conn
from core.disk_cache import search_cache
from core.models import SearchQuery
from core.sources import SOURCES, get_source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Búsqueda
# ---------------------------------------------------------------------------

@api_bp.route('/search')
def api_search():
    qs = SearchQuery(**request.args)
    if not qs.source:
        return jsonify({'error': 'Faltan parámetros type y source'}), 400

    cache_key = f"search:{qs.type}:{qs.source}:{qs.q}"

    if not qs.refresh:
        cached = search_cache.get(cache_key)
        if cached is not None:
            return jsonify(cached)

    source = get_source(qs.type, qs.source)
    if not source:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        results = source.search(qs.q)

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
            r.progress     = progress

        search_cache.set(cache_key, [r.model_dump() for r in results])
        return jsonify([r.model_dump() for r in results])
    except Exception as exc:
        logger.exception("Error en api_search:")
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/search-all')
def api_search_all():
    qs = SearchQuery(**request.args)

    cache_key = f"search_all:{qs.type}:{qs.q}"

    if not qs.refresh:
        cached = search_cache.get(cache_key)
        if cached is not None:
            return jsonify(cached)

    sources_dict = SOURCES.get(qs.type, {})
    if not sources_dict:
        return jsonify({'error': 'Tipo no soportado'}), 400

    def search_in_source(source_name: str, src) -> list:
        try:
            items = src.search(qs.q)
            for item in items:
                item.source = source_name
            return items
        except Exception as exc:
            logger.error(f"Error buscando en {source_name}: {exc}")
            return []

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(search_in_source, name, src): name
            for name, src in sources_dict.items()
        }
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    unique = {f"{r.source}:{r.id}": r for r in results}
    results = sorted(unique.values(), key=lambda x: x.title or '')

    search_cache.set(cache_key, [r.model_dump() for r in results])
    return jsonify([r.model_dump() for r in results])


_SSE_TIMEOUT = 90


@api_bp.route('/search-all-stream')
def api_search_all_stream():
    qs = SearchQuery(**request.args)
    if not qs.q:
        return jsonify({'error': 'Faltan parámetros type y q'}), 400

    sources_dict = SOURCES.get(qs.type, {})
    if not sources_dict:
        return jsonify({'error': 'Tipo no soportado'}), 400

    cache_key = f"search_all_stream:{qs.type}:{qs.q}"
    cached = search_cache.get(cache_key)
    if cached is not None:
        def _from_cache():
            for src_name, items in cached.items():
                yield f"event: results\ndata: {json.dumps({'source': src_name, 'results': items})}\n\n"
            yield "event: done\ndata: {}\n\n"
        return Response(_from_cache(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache'})

    def search_in_source(source_name: str, src) -> tuple[str, list]:
        try:
            items = src.search(qs.q)
            for item in items:
                item.source = source_name
            return source_name, [m.model_dump() for m in items]
        except Exception as exc:
            logger.error(f"Error buscando en {source_name}: {exc}")
            return source_name, []

    def generate():
        all_results: dict[str, list] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            fut_to_name = {
                executor.submit(search_in_source, name, src): name
                for name, src in sources_dict.items()
            }

            try:
                for future in concurrent.futures.as_completed(fut_to_name, timeout=_SSE_TIMEOUT):
                    source_name, items = future.result()
                    all_results[source_name] = items
                    yield f"event: results\ndata: {json.dumps({'source': source_name, 'results': items})}\n\n"
            except concurrent.futures.TimeoutError:
                for future in fut_to_name:
                    if future.done() and not future.cancelled():
                        try:
                            source_name, items = future.result()
                            if source_name not in all_results:
                                all_results[source_name] = items
                                yield f"event: results\ndata: {json.dumps({'source': source_name, 'results': items})}\n\n"
                        except Exception:
                            pass
                logger.warning(f"SSE search-all timeout tras {_SSE_TIMEOUT}s para '{qs.q}'")
            finally:
                for future in fut_to_name:
                    if not future.done():
                        future.cancel()

        if all_results:
            search_cache.set(cache_key, all_results)
        yield "event: done\ndata: {}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})
