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
from core.models import (
    DownloadChapterRequest,
    DownloadChaptersRequest,
    DownloadJob,
    DownloadRequest,
)
from core.sources import get_source
from core.utils import normalize_title
from .common import (
    _parse_json_body,
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
    data = _parse_json_body(DownloadRequest)

    src = get_source(data.type, data.source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")

    ref = get_content_ref(data.source, data.content_id)

    excluded_chapters: list[int] = []
    if data.exclude_watched:
        safe_title = normalize_title(data.title)
        watched    = get_watched_chapters(f"local:{safe_title}")
        excluded_chapters = list(watched)
        if excluded_chapters:
            logger.debug(f"Excluyendo {len(excluded_chapters)} capítulos vistos para '{data.title}'")

    existing = _queue_find_active(ref)
    if existing:
        return jsonify({'error': f"Ya está en cola (estado: {existing['status']})"}), 409

    job_id = _queue_insert(ref, data.type, data.title)
    download_queue.put(DownloadJob(
        id=job_id,
        content_ref=ref,
        type=data.type,
        title=data.title,
        excluded_chapters=excluded_chapters,
    ))
    return jsonify({'job_id': job_id, 'message': 'Descarga encolada'})


@api_bp.route('/download/chapter', methods=['POST'])
def api_download_chapter():
    data = _parse_json_body(DownloadChapterRequest)

    src = get_source(data.type, data.source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")

    ref = get_content_ref(data.source, data.content_id)

    existing = _queue_find_active(ref, data.chapter_id)
    if existing:
        return jsonify({'error': f"Ya está en cola (estado: {existing['status']})"}), 409

    job_id = _queue_insert(ref, data.type, data.title, data.chapter_id)
    download_queue.put(DownloadJob(
        id=job_id,
        content_ref=ref,
        type=data.type,
        title=data.title,
        chapter_id=data.chapter_id,
    ))
    return jsonify({'job_id': job_id, 'message': 'Capítulo encolado para descarga'})


@api_bp.route('/download/chapters', methods=['POST'])
def api_download_chapters():
    data = _parse_json_body(DownloadChaptersRequest)

    src = get_source(data.type, data.source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        save_content_to_db(data.type, data.source, data.content_id, data.title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {data.content_id}: {exc}")

    ref = get_content_ref(data.source, data.content_id)

    job_ids = []
    for ch_id in data.chapter_ids:
        existing = _queue_find_active(ref, ch_id)
        if existing:
            continue
        job_id = _queue_insert(ref, data.type, data.title, ch_id)
        download_queue.put(DownloadJob(
            id=job_id,
            content_ref=ref,
            type=data.type,
            title=data.title,
            chapter_id=ch_id,
        ))
        job_ids.append(job_id)

    return jsonify({
        'job_ids': job_ids,
        'count':   len(job_ids),
        'message': f'{len(job_ids)} de {len(data.chapter_ids)} capítulos encolados',
    })
