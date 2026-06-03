#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import concurrent.futures
import json
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR
from core.database import (
    DB_PATH,
    delete_watched_chapter,
    get_content_ref,
    get_progress,
    get_watched_chapters,
    get_conn,
    is_chapter_watched,
    mark_chapter_as_watched,
    save_content_to_db,
    save_progress,
    update_queue_status,
    set_series_status,
    get_series_status,
    get_all_series_statuses,
    get_series_to_check,
    mark_series_checked,
    get_last_checked,
    set_series_updates,
    get_series_with_updates,
    clear_series_updates,
)
from core.disk_cache import search_cache
from core.download_worker import download_queue, get_active_jobs
from core.sources import SOURCES, get_source
from core.utils import _normalize_path_name, normalize_title, scan_downloaded_series

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ---------------------------------------------------------------------------
# Índice en memoria: content_id → Path de carpeta local
# Se construye lazy la primera vez y se invalida cuando completa una descarga.
# Evita escanear todos los series_info.json en cada request.
# ---------------------------------------------------------------------------

_series_index: dict[str, dict[str, Path]] = {}   # base_dir_str → {content_id: Path}
_series_index_lock = threading.Lock()

def _build_series_index(base_dir: Path) -> dict[str, Path]:
    """Escanea base_dir UNA vez y devuelve {content_id: carpeta}."""
    index: dict[str, Path] = {}
    if not base_dir.exists():
        return index
    for cand_dir in base_dir.iterdir():
        if not cand_dir.is_dir():
            continue
        info_path = cand_dir / 'series_info.json'
        if info_path.exists():
            try:
                with open(info_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                cid = info.get('content_id')
                if cid:
                    index[cid] = cand_dir
            except Exception:
                pass
    return index


def _get_series_index(base_dir: Path) -> dict[str, Path]:
    """Devuelve el índice cacheado, construyéndolo si no existe."""
    key = str(base_dir)
    with _series_index_lock:
        if key not in _series_index:
            _series_index[key] = _build_series_index(base_dir)
        return _series_index[key]


def _invalidate_series_index(base_dir: Path | None = None) -> None:
    """Invalida el índice para que se reconstruya en el próximo acceso.
    Si base_dir es None, invalida todos los índices."""
    with _series_index_lock:
        if base_dir is None:
            _series_index.clear()
        else:
            _series_index.pop(str(base_dir), None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_path(base: str, untrusted: str) -> Path | None:
    """
    Resuelve `untrusted` dentro de `base` y verifica que no salga del directorio.
    Devuelve el Path resuelto o None si es un path traversal.
    """
    try:
        resolved = Path(base, untrusted).resolve()
        if resolved.is_relative_to(Path(base).resolve()):
            return resolved
    except Exception:
        pass
    return None


def _base_folder(content_type: str) -> str:
    return ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR


def _get_json() -> dict:
    """Devuelve el JSON del request o un dict vacío. Nunca lanza AttributeError."""
    return request.get_json(silent=True) or {}


def _require_local(content_ref: str):
    """Aborta con 400 si content_ref no es local."""
    if not content_ref.startswith('local:'):
        abort(jsonify({'error': 'Solo funciona con contenido local'}), 400)


# ---------------------------------------------------------------------------
# Queries de cola (reemplaza sqlite3.connect directo en el blueprint)
# ---------------------------------------------------------------------------

def _queue_find_active(content_ref: str, chapter_id: str | None = None) -> tuple | None:
    """Busca un job activo (pending/downloading) para un content_ref dado."""
    conn = get_conn()
    if chapter_id is not None:
        return conn.execute(
            'SELECT id, status FROM download_queue '
            'WHERE content_ref = ? AND chapter_id = ? AND status IN ("pending","downloading")',
            (content_ref, chapter_id)
        ).fetchone()
    return conn.execute(
        'SELECT id, status FROM download_queue '
        'WHERE content_ref = ? AND status IN ("pending","downloading")',
        (content_ref,)
    ).fetchone()


def _queue_insert(content_ref: str, content_type: str, title: str,
                  chapter_id: str | None = None) -> int:
    """Inserta un job en la cola y devuelve el id generado."""
    conn = get_conn()
    with conn:
        cur = conn.execute(
            'INSERT INTO download_queue (content_ref, type, title, chapter_id, status) '
            "VALUES (?, ?, ?, ?, 'pending')",
            (content_ref, content_type, title, chapter_id)
        )
    return cur.lastrowid


def _queue_get_status() -> tuple[list, list]:
    """Devuelve (active_jobs, pending_jobs) como listas de dicts."""
    conn = get_conn()

    active = [dict(r) for r in conn.execute(
        'SELECT id, content_ref, type, title, status, total_chapters, '
        'current_chapter, current_progress AS progress, error '
        'FROM download_queue WHERE status = "downloading" ORDER BY created_at ASC'
    ).fetchall()]

    pending = [dict(r) for r in conn.execute(
        'SELECT id, content_ref, type, title, status, total_chapters, '
        'current_chapter, current_progress AS progress '
        'FROM download_queue WHERE status = "pending" ORDER BY created_at ASC'
    ).fetchall()]

    return active, pending


def _content_title_by_ref(ref: str) -> str | None:
    conn = get_conn()
    row = conn.execute('SELECT title FROM content WHERE id = ?', (ref,)).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Helpers de sistema de archivos (reutilizados en varias rutas)
# ---------------------------------------------------------------------------

def _find_local_serie_dir(base_dir: Path, content_id: str) -> Path | None:
    """
    Busca la carpeta de una serie usando el índice en memoria (O(1)).
    El índice se construye la primera vez y se invalida al completar descargas.
    Fallback a normalización de nombre si no aparece en el índice.
    """
    index = _get_series_index(base_dir)

    # Método 1: índice en memoria — O(1)
    if content_id in index:
        candidate = index[content_id]
        if candidate.exists():       # podría haberse borrado en disco
            return candidate
        # La carpeta ya no existe: reconstruir índice y reintentar
        _invalidate_series_index(base_dir)
        index = _get_series_index(base_dir)
        if content_id in index:
            return index[content_id]

    # Método 2: fallback por normalización de nombre
    norm_id = _normalize_path_name(content_id)
    if base_dir.exists():
        for cand_dir in base_dir.iterdir():
            if cand_dir.is_dir() and _normalize_path_name(cand_dir.name) == norm_id:
                return cand_dir

    return None


def _local_chapters_anime(serie_dir: Path) -> list[dict]:
    chapters = []
    for f in sorted(serie_dir.glob("*.mp4")):
        m = re.search(r'_(\d+)\.mp4$', f.name)
        if m:
            num = int(m.group(1))
            chapters.append({'number': num, 'id': str(num)})
    return chapters


def _local_chapters_manga(serie_dir: Path) -> list[dict]:
    chapters = []
    for d in sorted(d for d in serie_dir.iterdir() if d.is_dir() and d.name.startswith('cap_')):
        m = re.search(r'cap_(\d+)', d.name)
        if m:
            num = int(m.group(1))
            chapters.append({'number': num, 'id': str(num)})
    return chapters


def _delete_chapter_files(serie_path: Path, content_type: str, chapter: int) -> None:
    """Elimina el archivo/carpeta de un capítulo del disco."""
    if content_type == 'anime':
        for f in serie_path.glob(f"*_{chapter:03d}.mp4"):
            f.unlink()
    else:
        cap_dir = serie_path / f"cap_{chapter:04d}"
        if cap_dir.exists() and cap_dir.is_dir():
            shutil.rmtree(cap_dir)


# ---------------------------------------------------------------------------
# Biblioteca
# ---------------------------------------------------------------------------

@api_bp.route('/library')
def api_library():
    return jsonify(scan_downloaded_series())


# ---------------------------------------------------------------------------
# Búsqueda
# ---------------------------------------------------------------------------

@api_bp.route('/search')
def api_search():
    content_type = request.args.get('type')
    source_name  = request.args.get('source')
    query        = request.args.get('q', '')
    refresh      = request.args.get('refresh', '0') == '1'

    if not content_type or not source_name:
        return jsonify({'error': 'Faltan parámetros type y source'}), 400

    cache_key = f"search:{content_type}:{source_name}:{query}"

    if not refresh:
        cached = search_cache.get(cache_key)
        if cached is not None:
            return jsonify(cached)

    source = get_source(content_type, source_name)
    if not source:
        return jsonify({'error': 'Fuente no encontrada'}), 404

    try:
        results = source.search(query)

        # Una sola query para todos los refs en lugar de N queries en loop
        refs = [get_content_ref(content_type, source_name, r['id']) for r in results]
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
            r['last_chapter'] = chapter
            r['progress']     = progress

        search_cache.set(cache_key, results)
        return jsonify(results)
    except Exception as exc:
        logger.exception("Error en api_search:")
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/search-all')
def api_search_all():
    content_type = request.args.get('type')
    query        = request.args.get('q', '')
    refresh      = request.args.get('refresh', '0') == '1'

    if not content_type or not query:
        return jsonify({'error': 'Faltan parámetros type y q'}), 400

    cache_key = f"search_all:{content_type}:{query}"

    if not refresh:
        cached = search_cache.get(cache_key)
        if cached is not None:
            return jsonify(cached)

    sources_dict = SOURCES.get(content_type, {})
    if not sources_dict:
        return jsonify({'error': 'Tipo no soportado'}), 400

    def search_in_source(source_name: str, src) -> list:
        try:
            items = src.search(query)
            for item in items:
                item['source'] = source_name
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

    # Deduplicar y ordenar
    unique = {f"{r['source']}:{r['id']}": r for r in results}
    results = sorted(unique.values(), key=lambda x: x.get('title', ''))

    search_cache.set(cache_key, results)
    return jsonify(results)


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
                           details['title'], details.get('cover', ''))
        return jsonify(details)
    except Exception as exc:
        logger.exception("Error en api_content_details:")
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/chapters/<content_type>/<source>/<content_id>')
def api_chapters(content_type, source, content_id):
    src = get_source(content_type, source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404
    try:
        return jsonify(src.get_chapters(content_id))
    except Exception as exc:
        logger.exception("Error en api_chapters:")
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/chapters/with-local/<type>/<source>/<id>')
def api_chapters_with_local(type, source, id):
    """Capítulos remotos marcando cuáles están descargados localmente."""
    src = get_source(type, source)
    if not src:
        return jsonify({'error': 'Fuente no encontrada'}), 404
    try:
        remote_chapters = src.get_chapters(id)

        # Reutiliza _find_local_serie_dir (índice en memoria) + helpers existentes
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
                num = int(float(ch['number']))
            except (TypeError, ValueError):
                num = None
            result.append({
                'number':        ch['number'],
                'id':            ch['id'],
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
    """Sirve portadas locales con protección contra path traversal."""
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
    """Sirve el archivo de video (anime)."""
    if content_type != 'anime':
        return jsonify({'message': 'Usa el visor de manga en el frontend'})

    ref = get_content_ref(content_type, source, content_id)
    title = _content_title_by_ref(ref)
    if not title:
        return jsonify({'error': 'Contenido no encontrado'}), 404

    safe_title = normalize_title(title)
    try:
        chap_num = int(float(chapter)) if chapter.replace('.', '', 1).isdigit() else 0
    except ValueError:
        return jsonify({'error': 'Capítulo inválido'}), 400

    filepath = Path(ANIME_DOWNLOAD_DIR) / safe_title / f"{safe_title}_{chap_num:03d}.mp4"
    if not filepath.exists():
        return jsonify({'error': 'Archivo no encontrado'}), 404
    return send_file(filepath, conditional=True)


@api_bp.route('/play/local/<type>/<id>/<chapter>')
def api_play_local(type, id, chapter):
    if type == 'anime':
        serie_dir = Path(ANIME_DOWNLOAD_DIR) / id
        if not serie_dir.exists():
            abort(404)
        try:
            chap_num = int(chapter)
        except ValueError:
            abort(400)
        files = list(serie_dir.glob(f"*_{chap_num:03d}.mp4"))
        if not files:
            abort(404)
        return send_file(files[0], conditional=True)
    else:
        serie_dir = Path(MANGA_DOWNLOAD_DIR) / id
        cap_dir   = serie_dir / f"cap_{int(chapter):04d}"
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
    """Sirve imágenes de manga con protección contra path traversal."""
    safe = _safe_path(MANGA_DOWNLOAD_DIR, subpath)
    if not safe:
        abort(403)
    if not safe.exists():
        abort(404)
    return send_file(safe)


@api_bp.route('/video-duration/anime/<content_id>/<chapter>')
def video_duration(content_id, chapter):
    """Duración de un video usando ffprobe. video_path viene de glob → no es input directo."""
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


# ---------------------------------------------------------------------------
# Progreso
# ---------------------------------------------------------------------------

@api_bp.route('/progress/<content_type>/<source>/<content_id>', methods=['GET', 'POST'])
def api_progress(content_type, source, content_id):
    ref = get_content_ref(content_type, source, content_id)
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
# Cola de descarga
# ---------------------------------------------------------------------------

@api_bp.route('/queue/status')
def api_queue_status():
    active, pending = _queue_get_status()
    return jsonify({'active': active, 'queue': pending})


@api_bp.route('/download', methods=['POST'])
def api_download():
    """Encola la descarga de una serie completa."""
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

    # NOTA: get_details() se ha movido al worker para no bloquear este request.
    # Guardamos en BD con el título que ya viene en el body (best-effort).
    try:
        save_content_to_db(content_type, source_name, content_id, title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {content_id}: {exc}")

    ref = get_content_ref(content_type, source_name, content_id)

    # Capítulos excluidos (ya vistos localmente)
    excluded_chapters: list[int] = []
    if exclude_watched:
        safe_title = normalize_title(title)
        watched    = get_watched_chapters(f"local:{safe_title}")
        excluded_chapters = list(watched)
        if excluded_chapters:
            logger.debug(f"Excluyendo {len(excluded_chapters)} capítulos vistos para '{title}'")

    # Verificar si ya está en cola
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
    """Encola la descarga de un capítulo individual."""
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

    # NOTA: get_details() se ha movido al worker. Guardamos con el título del body.
    try:
        save_content_to_db(content_type, source_name, content_id, title, '')
    except Exception as exc:
        logger.warning(f"No se pudo guardar content en BD para {content_id}: {exc}")

    ref = get_content_ref(content_type, source_name, content_id)

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
    """
    Encola la descarga de múltiples capítulos a la vez.
    Body: { type, source, content_id, title, chapter_ids: [...] }
    """
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

    ref = get_content_ref(content_type, source_name, content_id)

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
    """Elimina del disco todos los capítulos vistos de una serie local (excepto el último)."""
    data         = _get_json()
    content_ref  = data.get('content_ref')
    content_type = data.get('type')
    if not content_ref or not content_type:
        return jsonify({'error': 'Faltan parámetros'}), 400
    if not content_ref.startswith('local:'):
        return jsonify({'error': 'Solo funciona con contenido local'}), 400

    last_chapter_str, _ = get_progress(content_ref)
    last_chapter = int(last_chapter_str) if last_chapter_str else 0

    watched = get_watched_chapters(content_ref)
    if not watched:
        return jsonify({'message': 'No hay capítulos vistos para borrar'})

    folder_name = content_ref[6:]   # quita "local:"
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
    """Elimina un capítulo individual del disco."""
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
    if not content_ref.startswith('local:'):
        return jsonify({'error': 'Solo funciona con contenido local'}), 400

    folder_name = content_ref[6:]
    serie_path  = Path(_base_folder(content_type)) / folder_name
    if not serie_path.exists():
        return jsonify({'error': 'Carpeta no encontrada'}), 404

    try:
        _delete_chapter_files(serie_path, content_type, chapter)
    except Exception as exc:
        return jsonify({'error': f'Error al eliminar archivo: {exc}'}), 500

    # Si el capítulo eliminado era el último visto, retroceder el progreso
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
# Etiquetas de biblioteca (watching / completed / pending)
# ---------------------------------------------------------------------------

@api_bp.route('/library/status', methods=['GET'])
def api_library_statuses():
    """Devuelve todas las etiquetas en un solo request."""
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

@api_bp.route('/library/updates', methods=['GET'])
def api_library_updates():
    """
    Devuelve todas las series con capítulos nuevos pendientes.
    Para cada serie incluye content_ref y la lista de capítulos nuevos.
    El frontend usa esto para mostrar el badge global.
    """
    series = get_series_with_updates()
    # Resolver título de cada serie desde content / disco
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
    """
    Limpia el flag de novedades de una o varias series.
    Se llama cuando el usuario visita la página de una serie.
    Body: {'content_ref': '...'} o {'content_refs': ['...', '...']}
    """
    data = _get_json()
    refs = data.get('content_refs') or ([data.get('content_ref')] if data.get('content_ref') else [])
    if not refs:
        return jsonify({'error': 'Falta content_ref o content_refs'}), 400
    for ref in refs:
        clear_series_updates(ref)
    return jsonify({'cleared': len(refs)})


def _resolve_series_title(source_name: str, content_id: str) -> str:
    """Intenta resolver el título de una serie desde content DB o disco."""
    conn = get_conn()
    row = conn.execute(
        "SELECT title FROM content WHERE id = ?",
        (f"{source_name}:{content_id}",)
    ).fetchone()
    if row:
        return row[0]
    for ct, base in [('anime', ANIME_DOWNLOAD_DIR), ('manga', MANGA_DOWNLOAD_DIR)]:
        base_path = Path(base)
        serie_dir = _find_local_serie_dir(base_path, content_id)
        if serie_dir:
            info_path = serie_dir / 'series_info.json'
            if info_path.exists():
                try:
                    info = json.loads(info_path.read_text(encoding='utf-8'))
                    return info.get('title', content_id)
                except Exception:
                    pass
    return content_id


# ---------------------------------------------------------------------------
# Comprobación de actualizaciones (watching / completed)
# ---------------------------------------------------------------------------
 
def _check_series_for_new_chapters(content_ref: str) -> dict:
    """
    Lógica central de comprobación: compara capítulos remotos con locales.
    Devuelve un dict con el resultado y los capítulos nuevos encontrados.
    No lanza excepciones; las captura y las devuelve en 'error'.
    """
    try:
        # content_ref puede ser "source:content_id" o "local:folder_name"
        if content_ref.startswith('local:'):
            return {'content_ref': content_ref, 'new_chapters': [], 'error': 'Serie solo local, sin fuente remota'}
 
        source_name, content_id = content_ref.split(':', 1)
 
        # Detectar tipo leyendo series_info.json en disco
        content_type = None
        for ct, base in [('anime', ANIME_DOWNLOAD_DIR), ('manga', MANGA_DOWNLOAD_DIR)]:
            base_path = Path(base)
            serie_dir = _find_local_serie_dir(base_path, content_id)
            if serie_dir:
                content_type = ct
                local_dir    = serie_dir
                break
 
        if not content_type:
            return {'content_ref': content_ref, 'new_chapters': [], 'error': 'Serie no encontrada en disco'}
 
        src = get_source(content_type, source_name)
        if not src:
            return {'content_ref': content_ref, 'new_chapters': [], 'error': f"Fuente '{source_name}' no disponible"}
 
        # Capítulos remotos
        remote_chapters = src.get_chapters(content_id)
        remote_nums     = {int(float(ch['number'])) for ch in remote_chapters}
 
        # Capítulos locales
        if content_type == 'anime':
            local_list = _local_chapters_anime(local_dir)
        else:
            local_list = _local_chapters_manga(local_dir)
        local_nums = {ch['number'] for ch in local_list}
 
        new_nums = sorted(remote_nums - local_nums)

        remote_by_num = {int(float(ch['number'])): ch['id'] for ch in remote_chapters}
        new_chapter_ids = [remote_by_num[n] for n in new_nums if n in remote_by_num]

        mark_series_checked(content_ref)
        set_series_updates(content_ref, new_nums)

        return {
            'content_ref':     content_ref,
            'new_chapters':    new_nums,
            'new_chapter_ids': new_chapter_ids,
            'total_remote':    len(remote_nums),
            'total_local':     len(local_nums),
            'error':           None,
        }
 
    except Exception as exc:
        logger.exception(f"Error comprobando actualizaciones para {content_ref}:")
        return {'content_ref': content_ref, 'new_chapters': [], 'error': str(exc)}
 
 
@api_bp.route('/library/check-updates/<path:content_ref>', methods=['POST'])
def api_check_updates(content_ref):
    """
    Comprueba si hay capítulos nuevos para una serie concreta.
    Llamado por el botón manual en serie.html.
    Responde con los números de capítulo nuevos encontrados.
    """
    result = _check_series_for_new_chapters(content_ref)
    if result.get('error') and not result.get('new_chapters') is not None:
        return jsonify(result), 500
    return jsonify(result)
 
 
@api_bp.route('/library/check-all-updates', methods=['POST'])
def api_check_all_updates():
    """
    Comprueba todas las series con status 'watching' o 'completed'
    que no se han comprobado en las últimas 24 horas.
    Llamado por el scheduler automático o manualmente.
    """
    pending = get_series_to_check()
    if not pending:
        return jsonify({'checked': 0, 'results': [], 'message': 'No hay series pendientes de comprobación'})
 
    results = []
 
    # Comprobación paralela (mismo pool que search-all)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_check_series_for_new_chapters, s['content_ref']): s
            for s in pending
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
 
    series_with_updates = [r for r in results if r.get('new_chapters')]
    logger.info(
        f"check-all-updates: {len(results)} series comprobadas, "
        f"{len(series_with_updates)} con capítulos nuevos"
    )
    return jsonify({
        'checked':             len(results),
        'with_updates':        len(series_with_updates),
        'results':             results,
    })
