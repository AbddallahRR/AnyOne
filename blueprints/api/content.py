#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import subprocess
from pathlib import Path

from flask import abort, jsonify, send_file

from ..api import api_bp
from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR
from core.database import save_content_to_db
from core.sources import get_source
from core.utils import normalize_title
from .common import (
    _safe_path,
    _base_folder,
    _find_local_serie_dir,
    _local_chapters_anime,
    _local_chapters_manga,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detalles y capítulos (fuentes remotas)
# ---------------------------------------------------------------------------

@api_bp.route('/content/<content_type>/<source>/<content_id>')
def api_content_details(content_type, source, content_id):
    src = get_source(content_type, source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404
    try:
        details = src.get_details(content_id)
        save_content_to_db(content_type, source, content_id,
                           details.title, details.cover or '')
        return jsonify(details.model_dump())
    except Exception as exc:
        logger.exception("Error en api_content_details:")
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/chapters/<content_type>/<source>/<content_id>')
def api_chapters(content_type, source, content_id):
    src = get_source(content_type, source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404
    try:
        chapters = src.get_chapters(content_id)
        return jsonify([c.model_dump() for c in chapters])
    except Exception as exc:
        logger.exception("Error en api_chapters:")
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/chapters/with-local/<type>/<source>/<id>')
def api_chapters_with_local(type, source, id):
    src = get_source(type, source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404
    try:
        remote_chapters = src.get_chapters(id)
        base_dir  = Path(_base_folder(type))
        serie_dir = _find_local_serie_dir(base_dir, id)

        local_chapters: set[int] = set()
        if serie_dir:
            local_list = (_local_chapters_anime(serie_dir) if type == 'anime'
                          else _local_chapters_manga(serie_dir))
            local_chapters = {ch['number'] for ch in local_list}

        result = []
        for ch in remote_chapters:
            try:
                num = int(float(ch.number))
            except (TypeError, ValueError):
                num = None
            result.append({
                'number':        ch.number,
                'id':            ch.id,
                'is_downloaded': (num in local_chapters) if num is not None else False,
            })
        return jsonify(result)
    except Exception as exc:
        logger.exception("Error en api_chapters_with_local:")
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Contenido local
# ---------------------------------------------------------------------------

@api_bp.route('/content/local/<type>/<id>')
def api_local_content_details(type, id):
    normalized_id = normalize_title(id)
    serie_path = Path(_base_folder(type)) / normalized_id

    cover_url = ''
    for ext in ['jpg', 'jpeg', 'png', 'webp']:
        if (serie_path / f'cover.{ext}').exists():
            cover_url = f'/api/local-cover/{type}/{normalized_id}/cover.{ext}'
            break

    title    = id
    synopsis = 'Contenido descargado localmente.'
    info_path = serie_path / 'series_info.json'
    source_name = ''
    remote_id   = ''
    if info_path.exists():
        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                info = json.load(f)
            title      = info.get('title', id)
            synopsis   = info.get('synopsis', synopsis)
            source_name = info.get('source', '') or ''
            remote_id   = info.get('content_id', '') or ''
        except Exception:
            pass

    return jsonify({
        'title':    title,
        'cover':    cover_url,
        'synopsis': synopsis,
        'source':   source_name,
        'remote_id': remote_id,
    })


@api_bp.route('/chapters/local/<type>/<id>')
def api_local_chapters(type, id):
    base_dir  = Path(_base_folder(type))
    serie_dir = _find_local_serie_dir(base_dir, id)
    if not serie_dir:
        logger.debug(f"api_local_chapters: carpeta no encontrada para '{id}'")
        return jsonify([])

    if type == 'anime':
        return jsonify(_local_chapters_anime(serie_dir))
    return jsonify(_local_chapters_manga(serie_dir))


@api_bp.route('/local-cover/<type>/<path:filename>')
def local_cover(type, filename):
    base = _base_folder(type)
    safe = _safe_path(base, filename)
    if not safe:
        abort(403)
    if not safe.exists():
        abort(404)
    return send_file(safe)


# ---------------------------------------------------------------------------
# Reproducción / imágenes
# ---------------------------------------------------------------------------

@api_bp.route('/play/<content_type>/<source>/<content_id>/<chapter>')
def api_play(content_type, source, content_id, chapter):
    if content_type != 'anime':
        return jsonify({'message': 'Usa el visor de manga en el frontend'})

    try:
        chap_num = int(float(chapter)) if chapter.replace('.', '', 1).isdigit() else 0
    except ValueError:
        return jsonify({'error': 'Capítulo inválido'}), 400

    serie_dir = _find_local_serie_dir(Path(ANIME_DOWNLOAD_DIR), content_id)
    if not serie_dir:
        return jsonify({'error': 'Archivo no encontrado'}), 404

    filepath = serie_dir / f"{serie_dir.name}_{chap_num:03d}.mp4"
    if not filepath.exists():
        return jsonify({'error': 'Archivo no encontrado'}), 404
    return send_file(filepath, conditional=True)


@api_bp.route('/play/local/<type>/<id>/<chapter>')
def api_play_local(type, id, chapter):
    base = _base_folder(type)
    safe = _safe_path(base, id)
    if not safe:
        abort(403)
    if not safe.exists():
        abort(404)
    if type == 'anime':
        try:
            chap_num = int(chapter)
        except ValueError:
            abort(400)
        files = list(safe.glob(f"*_{chap_num:03d}.mp4"))
        if not files:
            abort(404)
        return send_file(files[0], conditional=True)
    else:
        try:
            cap_dir = safe / f"cap_{int(chapter):04d}"
        except ValueError:
            abort(400)
        if not cap_dir.exists():
            abort(404)
        images = (
            sorted(cap_dir.glob("*.jpg"))
            + sorted(cap_dir.glob("*.png"))
            + sorted(cap_dir.glob("*.webp"))
        )
        return jsonify([str(img.relative_to(MANGA_DOWNLOAD_DIR)) for img in images])


@api_bp.route('/manga/images/<path:subpath>')
def api_manga_images(subpath):
    safe = _safe_path(MANGA_DOWNLOAD_DIR, subpath)
    if not safe:
        abort(403)
    if not safe.exists():
        abort(404)
    return send_file(safe)


@api_bp.route('/video-duration/anime/<content_id>/<chapter>')
def video_duration(content_id, chapter):
    serie_dir = Path(ANIME_DOWNLOAD_DIR) / normalize_title(content_id)
    if not serie_dir.exists():
        abort(404)
    try:
        chap_num = int(chapter)
    except ValueError:
        abort(400)

    files = list(serie_dir.glob(f"*_{chap_num:03d}.mp4"))
    if not files:
        abort(404)

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(files[0])],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return jsonify({'duration': float(result.stdout.strip())})
    except Exception as exc:
        logger.error(f"Error obteniendo duración: {exc}")

    abort(500)
