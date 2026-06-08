#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import threading
import time
from pathlib import Path
from queue import Queue

from config import ANIME_DOWNLOAD_DIR, DOWNLOAD_NUM_WORKERS, MANGA_DOWNLOAD_DIR
from core.database import update_queue_status
from core.http_pool import HttpPool
from core.models import DownloadJob
from core.sources import get_source
from core.utils import _invalidate_scan_cache, normalize_title

logger = logging.getLogger(__name__)

download_queue: Queue = Queue(maxsize=50)

_active_jobs: dict[int, DownloadJob] = {}
_active_jobs_lock = threading.Lock()

_stop_event = threading.Event()


def _save_series_metadata(series_folder: str, title: str, source_name: str,
                           content_id: str, content_type: str, source) -> None:
    from core.database import save_content_to_db

    info_path    = os.path.join(series_folder, 'series_info.json')
    cover_filename = ''
    final_title  = title

    try:
        details   = source.get_details_sync(content_id)
        final_title = details.title or title
        cover_url = details.cover or ''

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
                    img_data = HttpPool.get_session().get(cover_url, headers=headers, timeout=30).content
                with open(cover_path, 'wb') as f:
                    f.write(img_data)
                logger.info(f"Portada guardada: {cover_path}")

                thumb_path = os.path.join(series_folder, 'thumb.webp')
                if not os.path.exists(thumb_path):
                    import subprocess
                    subprocess.run(
                        ['ffmpeg', '-y', '-i', cover_path,
                         '-vf', 'scale=200:-1:force_original_aspect_ratio=decrease',
                         '-q:v', '75', thumb_path],
                        capture_output=True, timeout=15
                    )

        try:
            save_content_to_db(content_type, source_name, content_id,
                               final_title, cover_filename)
        except Exception as db_exc:
            logger.warning(f"No se pudo actualizar BD para '{final_title}': {db_exc}")

    except Exception as exc:
        logger.error(f"Error descargando portada/detalles para '{title}': {exc}")
        cover_filename = ''

    info = {
        'title':      final_title,
        'source':     source_name,
        'content_id': content_id,
        'type':       content_type,
        'cover':      cover_filename,
    }
    with open(info_path, 'w', encoding='utf-8') as f:
        json.dump(info, f, ensure_ascii=False)


def _resolve_chapters(source, content_id: str, chapter_id: str | None,
                       excluded: list[int] | None = None) -> tuple[list, int]:
    all_chapters = source.get_chapters_sync(content_id)

    if chapter_id is not None:
        target = next((ch for ch in all_chapters if ch.id == chapter_id), None)
        if not target:
            raise Exception(f"Capítulo {chapter_id} no encontrado")
        logger.debug(f"Capítulo individual resuelto: {target}")
        return [target], 1

    if not all_chapters:
        raise Exception("No hay capítulos disponibles")

    if excluded is not None:
        original = len(all_chapters)
        all_chapters = [ch for ch in all_chapters if int(ch.number) not in excluded]
        if not all_chapters:
            raise Exception("Todos los capítulos están excluidos (ya vistos localmente)")
        logger.info(f"Excluidos {original - len(all_chapters)} capítulos ya vistos")

    return all_chapters, len(all_chapters)


def _download_worker(worker_id: int) -> None:
    logger.info(f"Worker {worker_id} listo")

    while not _stop_event.is_set():
        try:
            job: DownloadJob = download_queue.get(timeout=1)
        except Exception:
            continue

        with _active_jobs_lock:
            _active_jobs[job.id] = job

        job_id      = job.id
        content_ref = job.content_ref
        content_type = job.type
        title       = job.title
        chapter_id  = job.chapter_id
        excluded    = job.excluded_chapters

        source_name, content_id = content_ref.split(':', 1)
        source = get_source(content_type, source_name)

        try:
            if not source:
                raise Exception(f"Fuente '{source_name}' no encontrada")

            chapters, total = _resolve_chapters(source, content_id, chapter_id, excluded)

            update_queue_status(job_id, status='downloading',
                                total_chapters=total, current_chapter=0, current_progress=0)

            base_folder   = ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR
            safe_title    = normalize_title(title)
            series_folder = os.path.join(base_folder, safe_title)
            os.makedirs(series_folder, exist_ok=True)

            _save_series_metadata(series_folder, title, source_name,
                                  content_id, content_type, source)

            _LAST_DB_FLUSH = [time.time()]
            _FLUSH_INTERVAL = 30.0
            for idx, chapter in enumerate(chapters, start=1):
                chap_num = chapter.number
                chap_id  = chapter.id

                try:
                    source.download_chapter_sync(content_id, chap_id, series_folder, chap_num)
                except Exception as exc:
                    raise Exception(f"Error en capítulo {chap_num}: {exc}") from exc

                percent = int((idx / total) * 100)
                if chapter_id:
                    update_queue_status(job_id, status='completed', current_progress=100)
                else:
                    now = time.time()
                    if idx == total or now - _LAST_DB_FLUSH[0] >= _FLUSH_INTERVAL:
                        update_queue_status(job_id, current_chapter=idx, current_progress=percent)
                        _LAST_DB_FLUSH[0] = now
                        logger.debug(f"Job {job_id}: progreso {percent}% ({idx}/{total})")

            if not chapter_id:
                update_queue_status(job_id, status='completed', current_progress=100)

            try:
                from routers.api.common import _invalidate_series_index
                base = Path(ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR)
                _invalidate_series_index(base)
            except Exception:
                pass
            _invalidate_scan_cache()

            logger.info(f"Job {job_id} completado: '{title}'")

        except Exception as exc:
            logger.exception(f"Job {job_id} falló:")
            update_queue_status(job_id, status='failed', error=str(exc))

        finally:
            with _active_jobs_lock:
                _active_jobs.pop(job_id, None)
            download_queue.task_done()


def start_workers(n: int = DOWNLOAD_NUM_WORKERS) -> None:
    for i in range(n):
        t = threading.Thread(target=_download_worker, args=(i,), daemon=True)
        t.start()
        logger.info(f"Worker {i} iniciado")


def stop_workers():
    _stop_event.set()


def get_active_jobs() -> list[dict]:
    with _active_jobs_lock:
        return [j.model_dump() for j in _active_jobs.values()]
