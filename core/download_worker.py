#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

from core.database import update_queue_status
from core.download_progress import clear as clear_progress
from core.download_progress import report as report_progress
from core.http_pool import HttpPool
from core.models import DownloadJob
from core.settings import settings
from core.sources import get_source
from core.utils import _invalidate_scan_cache, normalize_title

logger = logging.getLogger(__name__)

download_queue: Queue = Queue(maxsize=50)

_active_jobs: dict[int, DownloadJob] = {}
_active_jobs_lock = threading.Lock()

_downloading_chapters: dict[str, set[str]] = {}
_dl_lock = threading.Lock()

_stop_event = threading.Event()

_postprocess_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ffmpeg")


def mark_downloading(folder: str, num: str) -> None:
    with _dl_lock:
        _downloading_chapters.setdefault(folder, set()).add(num)


def unmark_downloading(folder: str, num: str) -> None:
    with _dl_lock:
        s = _downloading_chapters.get(folder)
        if s:
            s.discard(num)
            if not s:
                del _downloading_chapters[folder]


def is_downloading(folder: str, num: str) -> bool:
    with _dl_lock:
        return num in _downloading_chapters.get(folder, set())


def _post_process_video(filepath: str) -> None:
    tmp = filepath + '.faststart.mp4'
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', filepath, '-c', 'copy',
             '-movflags', '+faststart', tmp],
            capture_output=True, timeout=120,
        )
        if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, filepath)
        else:
            stderr = (result.stderr or b'').decode(errors='replace').strip()
            logger.warning(f"faststart falló para {filepath}: {stderr[-300:] if stderr else 'sin salida'}")
    except FileNotFoundError:
        logger.warning("ffmpeg no encontrado, faststart omitido")
    except Exception as exc:
        logger.warning(f"faststart falló para {filepath}: {exc}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


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
                    try:
                        import subprocess
                        subprocess.run(
                            ['ffmpeg', '-y', '-i', cover_path,
                             '-vf', 'scale=200:-1:force_original_aspect_ratio=decrease',
                             '-q:v', '75', thumb_path],
                            capture_output=True, timeout=15
                        )
                    except Exception as thumb_exc:
                        logger.warning(f"No se pudo generar thumbnail para '{title}': {thumb_exc}")

        try:
            save_content_to_db(content_type, source_name, content_id,
                               final_title, cover_filename)
        except Exception as db_exc:
            logger.warning(f"No se pudo actualizar BD para '{final_title}': {db_exc}")

    except Exception as exc:
        logger.exception(f"Error descargando portada/detalles para '{title}': {exc}")
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
        all_chapters = [ch for ch in all_chapters if ch.number not in excluded]
        if not all_chapters:
            raise Exception("Todos los capítulos están excluidos (ya vistos localmente)")
        logger.info(f"Excluidos {original - len(all_chapters)} capítulos ya vistos")

    return all_chapters, len(all_chapters)


def _download_worker(worker_id: int) -> None:
    logger.info(f"Worker {worker_id} listo")

    while not _stop_event.is_set():
        try:
            job: DownloadJob = download_queue.get(timeout=1)
        except Exception as exc:
            logger.debug(f"Worker {worker_id}: queue timeout o interrupción: {exc}")
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

            base_folder   = str(settings.anime_download_dir) if content_type == 'anime' else str(settings.manga_download_dir)
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

                mark_downloading(series_folder, chap_num)
                result_path = None
                try:
                    max_retries = 2
                    last_exc = None
                    for attempt in range(1 + max_retries):
                        try:
                            result_path = source.download_chapter_sync(
                                content_id, chap_id, series_folder, chap_num,
                                progress_cb=lambda done, total, label='': report_progress(job_id, done, total, label),
                            )
                            last_exc = None
                            break
                        except Exception as exc:
                            last_exc = exc
                            if attempt < max_retries:
                                logger.warning(f"Job {job_id}: error en capítulo {chap_num} "
                                               f"(intento {attempt + 1}/{max_retries + 1}): {exc}")
                                time.sleep(2 ** attempt)  # backoff: 2s, 4s
                            else:
                                logger.exception(f"Job {job_id}: error definitivo en capítulo {chap_num} "
                                                 f"tras {max_retries + 1} intentos")

                    if last_exc is not None:
                        raise Exception(f"Error en capítulo {chap_num} tras {max_retries + 1} intentos: {last_exc}") from last_exc
                finally:
                    clear_progress(job_id)
                    unmark_downloading(series_folder, chap_num)

                if content_type == 'anime' and result_path:
                    _postprocess_pool.submit(_post_process_video, result_path)

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
                base = Path(str(settings.anime_download_dir) if content_type == 'anime' else str(settings.manga_download_dir))
                _invalidate_series_index(base)
            except Exception as exc:
                logger.debug(f"Job {job_id}: error invalidando índice de series: {exc}")
            _invalidate_scan_cache()

            logger.info(f"Job {job_id} completado: '{title}'")

        except Exception as exc:
            logger.exception(f"Job {job_id} falló:")
            update_queue_status(job_id, status='failed', error=str(exc))

        finally:
            with _active_jobs_lock:
                _active_jobs.pop(job_id, None)
            download_queue.task_done()


def start_workers(n: int | None = None) -> None:
    if n is None:
        n = settings.download_num_workers
    for i in range(n):
        t = threading.Thread(target=_download_worker, args=(i,), daemon=True)
        t.start()
        logger.info(f"Worker {i} iniciado")


def stop_workers():
    _stop_event.set()


def get_active_jobs() -> list[dict]:
    with _active_jobs_lock:
        return [j.model_dump() for j in _active_jobs.values()]
