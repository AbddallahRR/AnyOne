#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging

from flask import jsonify

from ..api import api_bp
from core.database import (
    save_content_to_db,
    get_content_ref,
    get_watched_chapters,
)
from core.download_worker import download_queue
from core.sources import get_source
from core.utils import normalize_title
from .common import (
    _get_json,
    _queue_find_active,
    _queue_insert,
    _queue_get_status,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cola de descarga
# ---------------------------------------------------------------------------

@api_bp.route('/queue/status')
def api_queue_status():
    active, pending = _queue_get_status()
    return jsonify({'active': active, 'queue': pending})


@api_bp.route('/download', methods=['POST'])
def api_download():
    data         = _get_json()
    content_type = data.get('type')
    source_name  = data.get('source')
    content_id   = data.get('content_id')
    title        = data.get('title')
    exclude_watched = data.get('exclude_watched', False)

    if not all([content_type, source_name, content_id, title]):
        return jsonify({'error': 'Faltan campos: type, source, content_id, title'}), 400

    src = get_source(content_type, source_name)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        save_content_to_db(content_type, source_name, content_id, title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {content_id}: {exc}")

    ref = get_content_ref(source_name, content_id)

    excluded_chapters: list[int] = []
    if exclude_watched:
        safe_title = normalize_title(title)
        watched    = get_watched_chapters(f"local:{safe_title}")
        excluded_chapters = list(watched)
        if excluded_chapters:
            logger.debug(f"Excluyendo {len(excluded_chapters)} capítulos vistos para '{title}'")

    existing = _queue_find_active(ref)
    if existing:
        return jsonify({'error': f"Ya está en cola (estado: {existing['status']})"}), 409

    job_id = _queue_insert(ref, content_type, title)
    download_queue.put({
        'id':                job_id,
        'content_ref':       ref,
        'type':              content_type,
        'title':             title,
        'excluded_chapters': excluded_chapters,
    })
    return jsonify({'job_id': job_id, 'message': 'Descarga encolada'})


@api_bp.route('/download/chapter', methods=['POST'])
def api_download_chapter():
    data           = _get_json()
    content_type   = data.get('type')
    source_name    = data.get('source')
    content_id     = data.get('content_id')
    chapter_id     = data.get('chapter_id')
    title          = data.get('title')

    if not all([content_type, source_name, content_id, title]):
        return jsonify({'error': 'Faltan campos: type, source, content_id, title'}), 400

    src = get_source(content_type, source_name)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        save_content_to_db(content_type, source_name, content_id, title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {content_id}: {exc}")

    ref = get_content_ref(source_name, content_id)

    existing = _queue_find_active(ref, chapter_id)
    if existing:
        return jsonify({'error': f"Ya está en cola (estado: {existing['status']})"}), 409

    job_id = _queue_insert(ref, content_type, title, chapter_id)
    download_queue.put({
        'id':          job_id,
        'content_ref': ref,
        'type':        content_type,
        'title':       title,
        'chapter_id':  chapter_id,
    })
    return jsonify({'job_id': job_id, 'message': 'Capítulo encolado para descarga'})


@api_bp.route('/download/chapters', methods=['POST'])
def api_download_chapters():
    data         = _get_json()
    content_type = data.get('type')
    source_name  = data.get('source')
    content_id   = data.get('content_id')
    title        = data.get('title')
    chapter_ids  = data.get('chapter_ids', [])

    if not all([content_type, source_name, content_id, title]):
        return jsonify({'error': 'Faltan campos: type, source, content_id, title'}), 400
    if not chapter_ids or not isinstance(chapter_ids, list):
        return jsonify({'error': 'chapter_ids debe ser una lista no vacía'}), 400

    src = get_source(content_type, source_name)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        save_content_to_db(content_type, source_name, content_id, title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {content_id}: {exc}")

    ref = get_content_ref(source_name, content_id)

    job_ids = []
    for ch_id in chapter_ids:
        existing = _queue_find_active(ref, ch_id)
        if existing:
            continue
        job_id = _queue_insert(ref, content_type, title, ch_id)
        download_queue.put({
            'id':          job_id,
            'content_ref': ref,
            'type':        content_type,
            'title':       title,
            'chapter_id':  ch_id,
        })
        job_ids.append(job_id)

    return jsonify({
        'job_ids': job_ids,
        'count':   len(job_ids),
        'message': f'{len(job_ids)} de {len(chapter_ids)} capítulos encolados',
    })
