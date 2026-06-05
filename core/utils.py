import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR


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
_SCAN_CACHE_TTL = 60.0

def _invalidate_scan_cache() -> None:
    global _scan_cache
    _scan_cache = None

def _scan_series_dir(serie_dir: Path, content_type: str) -> dict | None:
    """Escanea un directorio de serie y devuelve sus metadatos, o None si no es válido."""
    if content_type == 'anime':
        mp4_files = list(serie_dir.glob("*.mp4"))
        if not mp4_files:
            return None
        chapters = []
        for f in mp4_files:
            match = re.search(r'_(\d+)\.mp4$', f.name)
            if match:
                chapters.append(int(match.group(1)))
        last_chapter = max(chapters) if chapters else 0
    else:
        cap_dirs = [d for d in serie_dir.iterdir() if d.is_dir() and d.name.startswith('cap_')]
        if not cap_dirs:
            return None
        chapters = []
        for d in cap_dirs:
            match = re.search(r'cap_(\d+)', d.name)
            if match:
                chapters.append(int(match.group(1)))
        last_chapter = max(chapters) if chapters else 0

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
        except Exception:
            pass
    if not cover_url:
        for ext in ['jpg', 'jpeg', 'png', 'webp']:
            cover_file = serie_dir / f'cover.{ext}'
            if cover_file.exists():
                encoded_name = quote(serie_dir.name)
                cover_url = f"/api/local-cover/{content_type}/{encoded_name}/cover.{ext}"
                break

    # Preferir thumbnail WebP si existe
    if cover_url and (serie_dir / 'thumb.webp').exists():
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
    global _scan_cache, _scan_cache_time
    now = time.time()
    with _scan_cache_lock:
        if _scan_cache is not None and now - _scan_cache_time < _SCAN_CACHE_TTL:
            return _scan_cache

    series = []
    futures = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        for content_type, base_path in [('anime', ANIME_DOWNLOAD_DIR), ('manga', MANGA_DOWNLOAD_DIR)]:
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
            except Exception:
                pass

    # Enriquecer con BD (progreso + portada) — batch query única con LEFT JOIN
    from core.database import get_conn
    conn = get_conn()
    refs = [f"local:{s['id']}" for s in series]
    if refs:
        placeholders = ','.join('?' * len(refs))
        rows = conn.execute(
            f'''SELECT c.id, c.cover, p.chapter, p.progress
                FROM content c
                LEFT JOIN user_progress p ON p.content_id = c.id
                WHERE c.id IN ({placeholders})''',
            refs
        ).fetchall()
        enrichment = {r[0]: (r[1], r[2], r[3]) for r in rows}

        for s in series:
            ref = f"local:{s['id']}"
            entry = enrichment.get(ref)
            if entry:
                cover, chapter, progress = entry
                if chapter:
                    s['last_chapter'] = chapter
                    s['progress'] = progress or '0'
                if cover and not s['cover']:
                    s['cover'] = cover
            if s['last_chapter'] == '0':
                s['last_chapter'] = '1'

    with _scan_cache_lock:
        _scan_cache = series
        _scan_cache_time = time.time()
    return series
