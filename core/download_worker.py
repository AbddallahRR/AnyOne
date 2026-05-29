#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import threading
from queue import Queue

import requests

from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR
from core.database import update_queue_status
from core.sources import get_source
from core.utils import normalize_title

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Estado compartido
# ---------------------------------------------------------------------------

download_queue: Queue = Queue()

# dict en lugar de lista: O(1) para agregar/quitar, sin búsqueda lineal
_active_jobs: dict[int, dict] = {}
_active_jobs_lock = threading.Lock()

# Leer de config si existe, sino usar 3 por defecto
try:
    from config import DOWNLOAD_NUM_WORKERS as NUM_WORKERS  # type: ignore[attr-defined]
except ImportError:
    NUM_WORKERS = 3


# ---------------------------------------------------------------------------
# Metadatos de serie
# ---------------------------------------------------------------------------

def _save_series_metadata(series_folder: str, title: str, source_name: str,
                           content_id: str, content_type: str, source) -> None:
    """
    Descarga la portada (si no existe) y escribe series_info.json.
    Ahora también actualiza la BD con el título/portada definitivos desde la fuente
    (los que antes se obtenían en api_download, que ahora encola sin bloquear).
    Llamar ANTES del bucle de capítulos; los errores son no-fatales.
    """
    from core.database import save_content_to_db   # import local para evitar ciclo

    info_path    = os.path.join(series_folder, 'series_info.json')
    cover_filename = ''
    final_title  = title   # puede mejorarse con get_details

    try:
        details   = source.get_details(content_id)
        final_title = details.get('title', title)
        cover_url = details.get('cover', '')

        if cover_url:
            ext = cover_url.split('.')[-1].split('?')[0].lower()
            if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
                ext = 'jpg'
            cover_filename = f'cover.{ext}'
            cover_path     = os.path.join(series_folder, cover_filename)

            if not os.path.exists(cover_path):
                headers = {'User-Agent': source.UA} if hasattr(source, 'UA') else {}
                if hasattr(source, 'scraper'):
                    img_data = source.scraper.get(cover_url, headers=headers).content
                else:
                    img_data = requests.get(cover_url, headers=headers, timeout=30).content
                with open(cover_path, 'wb') as f:
                    f.write(img_data)
                logger.info(f"Portada guardada: {cover_path}")

        # Actualizar BD con datos definitivos (título real + portada)
        try:
            save_content_to_db(content_type, source_name, content_id,
                               final_title, cover_filename)
        except Exception as db_exc:
            logger.warning(f"No se pudo actualizar BD para '{final_title}': {db_exc}")

    except Exception as exc:
        logger.error(f"Error descargando portada/detalles para '{title}': {exc}")
        cover_filename = ''  # no rompe la descarga

    info = {
        'title':      final_title,
        'source':     source_name,
        'content_id': content_id,
        'type':       content_type,
        'cover':      cover_filename,
    }
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Lógica de preparación del job
# ---------------------------------------------------------------------------

def _resolve_chapters(source, content_id: str, chapter_id: str | None,
                       excluded: list[int]) -> tuple[list, int]:
    """
    Llama a get_chapters UNA sola vez y devuelve (chapters_a_descargar, total).
    Lanza Exception si no hay capítulos válidos.
    """
    all_chapters = source.get_chapters(content_id)

    if chapter_id is not None:
        # Capítulo individual
        target = next((ch for ch in all_chapters if str(ch['id']) == str(chapter_id)), None)
        if not target:
            raise Exception(f"Capítulo {chapter_id} no encontrado")
        logger.debug(f"Capítulo individual resuelto: {target}")
        return [target], 1

    # Serie completa
    if not all_chapters:
        raise Exception("No hay capítulos disponibles")

    if excluded:
        original = len(all_chapters)
        all_chapters = [ch for ch in all_chapters if int(ch['number']) not in excluded]
        if not all_chapters:
            raise Exception("Todos los capítulos están excluidos (ya vistos localmente)")
        logger.info(f"Excluidos {original - len(all_chapters)} capítulos ya vistos")

    return all_chapters, len(all_chapters)


# ---------------------------------------------------------------------------
# Worker principal
# ---------------------------------------------------------------------------

def _download_worker(worker_id: int) -> None:
    """Función de cada hilo worker. Loop infinito procesando la cola."""
    logger.info(f"Worker {worker_id} listo")

    while True:
        job = download_queue.get()

        with _active_jobs_lock:
            _active_jobs[job['id']] = job

        job_id      = job['id']
        content_ref = job['content_ref']
        content_type = job['type']
        title       = job['title']
        chapter_id  = job.get('chapter_id')          # None → serie completa
        excluded    = job.get('excluded_chapters', [])

        source_name, content_id = content_ref.split(':', 1)
        source = get_source(content_type, source_name)

        try:
            if not source:
                raise Exception(f"Fuente '{source_name}' no encontrada")

            # ── 1. Resolver capítulos (UNA sola petición HTTP) ──────────────
            chapters, total = _resolve_chapters(source, content_id, chapter_id, excluded)

            update_queue_status(job_id, status='downloading',
                                total_chapters=total, current_chapter=0, current_progress=0)

            # ── 2. Preparar carpeta de destino ───────────────────────────────
            base_folder   = ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR
            safe_title    = normalize_title(title)
            series_folder = os.path.join(base_folder, safe_title)
            os.makedirs(series_folder, exist_ok=True)

            # ── 3. Metadatos (portada + series_info.json) ────────────────────
            _save_series_metadata(series_folder, title, source_name,
                                  content_id, content_type, source)

            # ── 4. Bucle de descarga ─────────────────────────────────────────
            _PROGRESS_EVERY = 5   # actualizar BD cada N capítulos (reduce I/O ~80%)
            for idx, chapter in enumerate(chapters, start=1):
                chap_num = chapter['number']
                chap_id  = chapter['id']

                try:
                    source.download_chapter(content_id, chap_id, series_folder)
                except Exception as exc:
                    raise Exception(f"Error en capítulo {chap_num}: {exc}") from exc

                percent = int((idx / total) * 100)
                if chapter_id:
                    # Capítulo individual: marcar completado al terminar el único capítulo
                    update_queue_status(job_id, status='completed', current_progress=100)
                else:
                    # Throttle: actualizar solo cada N caps o en el último
                    if idx % _PROGRESS_EVERY == 0 or idx == total:
                        update_queue_status(job_id, current_chapter=idx, current_progress=percent)
                        logger.debug(f"Job {job_id}: progreso {percent}% ({idx}/{total})")

            # ── 5. Finalizar ─────────────────────────────────────────────────
            if not chapter_id:
                update_queue_status(job_id, status='completed', current_progress=100)

            # Invalidar el índice en memoria para que la nueva serie aparezca
            try:
                from blueprints.api import _invalidate_series_index
                from pathlib import Path as _Path
                base = _Path(ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR)
                _invalidate_series_index(base)
            except Exception:
                pass   # no es crítico

            logger.info(f"Job {job_id} completado: '{title}'")

        except Exception as exc:
            logger.exception(f"Job {job_id} falló:")
            update_queue_status(job_id, status='failed', error=str(exc))

        finally:
            with _active_jobs_lock:
                _active_jobs.pop(job_id, None)
            download_queue.task_done()


# ---------------------------------------------------------------------------
# API pública: iniciar workers desde create_app()
# ---------------------------------------------------------------------------

def start_workers(n: int = NUM_WORKERS) -> None:
    """
    Inicia los hilos workers. Llamar una sola vez desde create_app().
    No se inicia automáticamente al importar el módulo.
    """
    for i in range(n):
        t = threading.Thread(target=_download_worker, args=(i,), daemon=True)
        t.start()
        logger.info(f"Worker {i} iniciado")


def get_active_jobs() -> list[dict]:
    """Devuelve una copia de los jobs actualmente en proceso."""
    with _active_jobs_lock:
        return list(_active_jobs.values())