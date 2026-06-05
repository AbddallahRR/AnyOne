#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from pathlib import Path

from flask import jsonify, request

from ..api import api_bp
from core.database import (
    delete_watched_chapter,
    get_content_ref,
    get_progress,
    get_watched_chapters,
    get_conn,
    is_chapter_watched,
    mark_chapter_as_watched,
    save_progress,
    set_series_status,
    get_series_status,
    get_all_series_statuses,
    get_series_with_updates,
    clear_series_updates,
)
from core.utils import scan_downloaded_series
from .common import (
    _get_json,
    _require_local,
    _base_folder,
    _delete_chapter_files,
    _resolve_series_title,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Biblioteca
# ---------------------------------------------------------------------------

@api_bp.route('/library')
def api_library():
    return jsonify(scan_downloaded_series())


# ---------------------------------------------------------------------------
# Etiquetas de biblioteca (watching / completed / pending)
# ---------------------------------------------------------------------------

@api_bp.route('/library/status', methods=['GET'])
def api_library_statuses():
    return jsonify(get_all_series_statuses())


@api_bp.route('/library/status/<path:content_ref>', methods=['GET'])
def api_get_series_status(content_ref):
    return jsonify({'content_ref': content_ref, 'status': get_series_status(content_ref)})


@api_bp.route('/library/status', methods=['POST'])
def api_set_series_status():
    data        = _get_json()
    content_ref = data.get('content_ref')
    status      = data.get('status', 'none')
    if not content_ref:
        return jsonify({'error': 'Falta content_ref'}), 400
    if status not in ('watching', 'completed', 'pending', 'none'):
        return jsonify({'error': f"Estado inválido: {status}"}), 400
    set_series_status(content_ref, status)
    return jsonify({'status': status})


# ---------------------------------------------------------------------------
# Progreso
# ---------------------------------------------------------------------------

@api_bp.route('/progress/<content_type>/<source>/<content_id>', methods=['GET', 'POST'])
def api_progress(content_type, source, content_id):
    ref = get_content_ref(source, content_id)
    if request.method == 'GET':
        chapter, progress = get_progress(ref)
        return jsonify({'chapter': chapter, 'progress': progress})

    data     = _get_json()
    chapter  = data.get('chapter', '1')
    progress = data.get('progress', '0')
    save_progress(ref, chapter, progress)
    return jsonify({'status': 'ok'})


@api_bp.route('/progress/local/<type>/<id>', methods=['GET', 'POST'])
def api_local_progress(type, id):
    ref = f"local:{id}"
    if request.method == 'GET':
        chapter, progress = get_progress(ref)
        return jsonify({'chapter': chapter, 'progress': progress})

    data     = _get_json()
    chapter  = data.get('chapter', '1')
    progress = data.get('progress', '0')
    save_progress(ref, chapter, progress)
    return jsonify({'status': 'ok'})


# ---------------------------------------------------------------------------
# Capítulos vistos
# ---------------------------------------------------------------------------

@api_bp.route('/watched', methods=['POST'])
def api_mark_watched():
    data        = _get_json()
    content_ref = data.get('content_ref')
    chapter     = data.get('chapter')
    if not content_ref or chapter is None:
        return jsonify({'error': 'Faltan parámetros'}), 400
    mark_chapter_as_watched(content_ref, chapter)
    return jsonify({'status': 'ok'})


@api_bp.route('/watched/<path:content_ref>')
def api_get_watched(content_ref):
    return jsonify({'watched': get_watched_chapters(content_ref)})


@api_bp.route('/watched/toggle', methods=['POST'])
def api_toggle_watched():
    data        = _get_json()
    content_ref = data.get('content_ref')
    chapter     = data.get('chapter')
    if not content_ref or chapter is None:
        return jsonify({'error': 'Faltan parámetros'}), 400

    if is_chapter_watched(content_ref, chapter):
        delete_watched_chapter(content_ref, chapter)
        return jsonify({'status': 'unwatched'})
    mark_chapter_as_watched(content_ref, chapter)
    return jsonify({'status': 'watched'})


@api_bp.route('/delete-watched', methods=['POST'])
def api_delete_watched():
    data         = _get_json()
    content_ref  = data.get('content_ref')
    content_type = data.get('type')
    if not content_ref or not content_type:
        return jsonify({'error': 'Faltan parámetros'}), 400
    _require_local(content_ref)

    last_chapter_str, _ = get_progress(content_ref)
    last_chapter = int(last_chapter_str) if last_chapter_str else 0

    watched = get_watched_chapters(content_ref)
    if not watched:
        return jsonify({'message': 'No hay capítulos vistos para borrar'})

    folder_name = content_ref[6:]
    serie_path  = Path(_base_folder(content_type)) / folder_name
    if not serie_path.exists():
        return jsonify({'error': 'Carpeta no encontrada'}), 404

    deleted = []
    for chap in watched:
        if chap == last_chapter:
            continue
        try:
            _delete_chapter_files(serie_path, content_type, chap)
            delete_watched_chapter(content_ref, chap)
            deleted.append(chap)
        except Exception as exc:
            logger.error(f"Error borrando capítulo {chap} de '{content_ref}': {exc}")

    return jsonify({'deleted': deleted, 'message': f'Se eliminaron {len(deleted)} capítulos vistos'})


@api_bp.route('/delete-chapter', methods=['POST'])
def api_delete_chapter():
    data         = _get_json()
    content_ref  = data.get('content_ref')
    content_type = data.get('type')
    chapter_str  = data.get('chapter')

    if not content_ref or not content_type or chapter_str is None:
        return jsonify({'error': 'Faltan parámetros'}), 400
    try:
        chapter = int(chapter_str)
    except (TypeError, ValueError):
        return jsonify({'error': 'Capítulo inválido'}), 400
    _require_local(content_ref)

    folder_name = content_ref[6:]
    serie_path  = Path(_base_folder(content_type)) / folder_name
    if not serie_path.exists():
        return jsonify({'error': 'Carpeta no encontrada'}), 404

    try:
        _delete_chapter_files(serie_path, content_type, chapter)
    except Exception as exc:
        return jsonify({'error': f'Error al eliminar archivo: {exc}'}), 500

    last_chapter_str, _ = get_progress(content_ref)
    try:
        if int(last_chapter_str) == chapter:
            if content_type == 'anime':
                remaining = sorted(int(f.stem.split('_')[-1]) for f in serie_path.glob("*.mp4"))
            else:
                remaining = sorted(
                    int(d.name[4:]) for d in serie_path.iterdir()
                    if d.is_dir() and d.name.startswith('cap_')
                )
            new_last = str(max(remaining)) if remaining else '1'
            save_progress(content_ref, new_last, '0')
    except Exception as exc:
        logger.warning(f"No se pudo actualizar progreso tras eliminar capítulo {chapter}: {exc}")

    return jsonify({'status': 'deleted', 'chapter': chapter})


# ---------------------------------------------------------------------------
# Novedades (updates)
# ---------------------------------------------------------------------------

@api_bp.route('/library/updates', methods=['GET'])
def api_library_updates():
    series = get_series_with_updates()
    results = []
    for s in series:
        parts = s['content_ref'].split(':', 1)
        if len(parts) == 2:
            source_name, content_id = parts
            title = _resolve_series_title(source_name, content_id)
        else:
            title = s['content_ref']
        results.append({
            'content_ref':  s['content_ref'],
            'title':        title,
            'new_chapters': s['new_chapters'],
        })
    return jsonify({
        'total':  len(results),
        'series': results,
    })


@api_bp.route('/library/acknowledge-updates', methods=['POST'])
def api_acknowledge_updates():
    data = _get_json()
    refs = data.get('content_refs') or ([data.get('content_ref')] if data.get('content_ref') else [])
    if not refs:
        return jsonify({'error': 'Falta content_ref o content_refs'}), 400
    for ref in refs:
        clear_series_updates(ref)
    return jsonify({'cleared': len(refs)})
