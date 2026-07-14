import json
import logging
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

from core.chapter_utils import chapter_float_key, normalize_chapter_number
from core.settings import settings

logger = logging.getLogger(__name__)


def normalize_title(raw_title):
    """Limpia títulos para usarlos como nombre de carpeta."""
    title = unicodedata.normalize('NFKD', raw_title).encode('ASCII', 'ignore').decode('ASCII')
    title = re.sub(r'[\\/*?:"<>|.,;=+[\]{}()&$#!`~]', '_', title)
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.replace(' ', '_')
    if len(title) > 100:
        title = title[:100].rstrip('_')
    return title

def _normalize_path_name(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = re.sub(r'[-\s_?¿!¡]+', ' ', text)
    return text.strip()

def normalize_for_comparison(text):
    """Normaliza texto para comparación (sin tildes, minúsculas, solo alfanuméricos)."""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()
_scan_cache: list | None = None
_scan_cache_time: float = 0.0
_scan_cache_lock = threading.Lock()
_scan_cache_gen = 0
_SCAN_CACHE_TTL = 300.0


def _invalidate_scan_cache() -> None:
    global _scan_cache, _scan_cache_gen
    with _scan_cache_lock:
        _scan_cache = None
        _scan_cache_gen += 1

def _scan_series_dir(serie_dir: Path, content_type: str) -> dict | None:
    """Escanea un directorio de serie y devuelve sus metadatos, o None si no es válido."""
    if content_type == 'anime':
        mp4_files = list(serie_dir.glob("*.mp4"))
        if not mp4_files:
            return None
        chapters = []
        for f in mp4_files:
            match = re.search(r'^(\d+)\.mp4$', f.name)
            if match:
                chapters.append(int(match.group(1)))
        last_chapter = max(chapters) if chapters else 0
    else:
        cap_dirs = [d for d in serie_dir.iterdir() if d.is_dir() and d.name.startswith('cap_')]
        if not cap_dirs:
            return None
        chapters = []
        for d in cap_dirs:
            match = re.search(r'cap_(\d[\d._]*)', d.name)
            if match:
                chapters.append(normalize_chapter_number(match.group(1)))
        if chapters:
            last_chapter = max(chapters, key=lambda c: chapter_float_key(c.split('_')[0]))
        else:
            last_chapter = 0

    cover_url = ''
    info_path = serie_dir / 'series_info.json'
    if info_path.exists():
        try:
            with open(info_path, 'r') as f:
                info = json.load(f)
                cover_filename = info.get('cover', '')
                if cover_filename:
                    encoded_name = quote(serie_dir.name)
                    cover_url = f"/api/local-cover/{content_type}/{encoded_name}/{cover_filename}"
        except Exception as exc:
            logger.debug('utils: error leyendo info.json para portada: %s', exc)
    if not cover_url:
        for ext in ['jpg', 'jpeg', 'png', 'webp']:
            cover_file = serie_dir / f'cover.{ext}'
            if cover_file.exists():
                encoded_name = quote(serie_dir.name)
                cover_url = f"/api/local-cover/{content_type}/{encoded_name}/cover.{ext}"
                break

    # Preferir thumbnail WebP si existe (reduce ancho de banda),
    # pero no si la portada original ya es WebP (puede ser animada)
    if cover_url and (serie_dir / 'thumb.webp').exists() and not (serie_dir / 'cover.webp').exists():
        encoded_name = quote(serie_dir.name)
        cover_url = f"/api/local-cover/{content_type}/{encoded_name}/thumb.webp?thumb=1"

    return {
        'type': content_type,
        'id': serie_dir.name,
        'title': serie_dir.name.replace('_', ' ').title(),
        'cover': cover_url,
        'last_chapter': str(last_chapter),
        'progress': '0'
    }


def scan_downloaded_series():
    global _scan_cache, _scan_cache_time, _scan_cache_gen
    now = time.time()
    with _scan_cache_lock:
        if _scan_cache is not None and now - _scan_cache_time < _SCAN_CACHE_TTL:
            return _scan_cache
        _scan_cache = None  # invalidate while scanning
        start_gen = _scan_cache_gen

    series = []
    futures = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        for content_type, base_path in [('anime', str(settings.anime_download_dir)), ('manga', str(settings.manga_download_dir))]:
            base = Path(base_path)
            if not base.exists():
                continue
            for serie_dir in base.iterdir():
                if not serie_dir.is_dir():
                    continue
                futures.append(executor.submit(_scan_series_dir, serie_dir, content_type))

        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    series.append(result)
            except Exception as exc:
                logger.debug('utils: error en future.result() para serie local: %s', exc)

    # Enriquecer con BD (progreso + portada) — JOIN único
    from core.database import get_conn
    conn = get_conn()
    refs = [f"local:{s['id']}" for s in series]
    if refs:
        placeholders = ','.join('?' * len(refs))
        rows = conn.execute(
            f'SELECT up.content_id, up.chapter, up.progress, c.cover '
            f'FROM user_progress up LEFT JOIN content c ON c.id = up.content_id '
            f'WHERE up.content_id IN ({placeholders})',
            refs
        ).fetchall()
        prog_map = {r[0]: (r[1], r[2]) for r in rows}
        cover_map = {r[0]: r[3] for r in rows if r[3]}

        for s in series:
            ref = f"local:{s['id']}"
            prog = prog_map.get(ref)
            if prog:
                chapter, progress = prog
                if chapter:
                    parts = chapter.split('.')
                    parts[0] = parts[0].lstrip('0') or '0'
                    s['progress_chapter'] = '.'.join(parts)
                    s['progress'] = progress or '0'
            if not s['cover']:
                s['cover'] = cover_map.get(ref, '')
            if s['last_chapter'] == '0':
                s['last_chapter'] = '1'

    with _scan_cache_lock:
        if _scan_cache_gen == start_gen:
            _scan_cache = series
            _scan_cache_time = time.time()
    return series


def count_images_in_dir(cap_dir: str) -> int:
    from pathlib import Path
    exts = {'.jpg', '.jpeg', '.png', '.webp'}
    try:
        return sum(
            1 for f in Path(cap_dir).iterdir()
            if f.is_file() and f.suffix.lower() in exts
        )
    except FileNotFoundError:
        return 0
