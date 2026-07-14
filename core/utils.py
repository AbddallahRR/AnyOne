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


def _get_image_dimensions_from_bytes(data: bytes) -> tuple[int, int] | None:
    """
    Extract image dimensions from raw bytes without full decode.
    Returns (width, height) or None if unable to determine.
    """
    if len(data) < 8:
        return None

    # PNG: IHDR chunk at offset 16 contains width (4 bytes BE) and height (4 bytes BE)
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        if len(data) >= 24:
            width = int.from_bytes(data[16:20], 'big')
            height = int.from_bytes(data[20:24], 'big')
            return (width, height)
        return None

    # JPEG: look for SOF0 (0xFFC0) or SOF2 (0xFFC2) marker
    if data[:2] == b'\xff\xd8':
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC2):  # SOF0 or SOF2
                height = int.from_bytes(data[i + 5:i + 7], 'big')
                width = int.from_bytes(data[i + 7:i + 9], 'big')
                return (width, height)
            # Skip to next marker
            if marker == 0xD9 or marker == 0xDA:  # EOI or SOS
                break
            seg_len = int.from_bytes(data[i + 2:i + 4], 'big')
            i += 2 + seg_len
        return None

    # WebP: RIFF header, then check for VP8 or VP8L chunk
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        if data[12:16] == b'VP8 ' and len(data) >= 30:
            # Lossy WebP: dimensions at offset 26 (3 bytes each)
            width = int.from_bytes(data[26:28], 'little') & 0x3FFF
            height = int.from_bytes(data[28:30], 'little') & 0x3FFF
            return (width, height)
        if data[12:16] == b'VP8L' and len(data) >= 25:
            # Lossless WebP: dimensions packed in 4 bytes at offset 21
            bits = int.from_bytes(data[21:25], 'little')
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return (width, height)
        return None

    # GIF: dimensions at offset 6
    if data[:6] in (b'GIF87a', b'GIF89a') and len(data) >= 10:
        width = int.from_bytes(data[6:8], 'little')
        height = int.from_bytes(data[8:10], 'little')
        return (width, height)

    # BMP: dimensions at offset 18
    if data[:2] == b'BM' and len(data) >= 26:
        width = int.from_bytes(data[18:22], 'little')
        height = abs(int.from_bytes(data[22:26], 'little'))
        return (width, height)

    return None


def filter_manga_images(
    image_urls: list[str],
    min_dimension: int = 300,
    max_workers: int = 16,
) -> list[str]:
    """
    Filter manga image URLs by checking actual image dimensions.
    Streams only the first bytes of each image to read headers.
    Returns only URLs where both width AND height >= min_dimension.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from core.http_pool import HttpPool
    from core.throttle import rate_limiter

    if not image_urls:
        return []

    _HEADER_BYTES = 32768  # 32KB — enough for PNG IHDR, JPEG SOF, WebP VP8 headers

    def _check_one(url: str) -> str | None:
        try:
            rate_limiter.wait(url)
            sc = HttpPool.get_scraper()
            resp = sc.get(
                url,
                headers={'Range': f'bytes=0-{_HEADER_BYTES - 1}'},
                timeout=10,
                stream=True,
            )
            # Read only up to _HEADER_BYTES even if server ignores Range
            data = b''
            for chunk in resp.iter_content(chunk_size=8192):
                data += chunk
                if len(data) >= _HEADER_BYTES:
                    break
            resp.close()

            dims = _get_image_dimensions_from_bytes(data)
            if dims is None:
                return None  # can't determine → keep it to be safe
            w, h = dims
            if w < min_dimension or h < min_dimension:
                logger.debug(f"filter_manga_images: descartada imagen pequeña {w}x{h}: {url[:80]}")
                return None
            return url
        except Exception as exc:
            logger.debug(f"filter_manga_images: error verificando {url[:80]}: {exc}")
            return None  # on error → keep the image

    filtered: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_check_one, url): url for url in image_urls}
        for future in as_completed(futures):
            original_url = futures[future]
            try:
                result = future.result()
                if result is not None:
                    filtered.append(result)
            except Exception:
                filtered.append(original_url)  # keep on error

    # Maintain original order
    url_set = set(filtered)
    ordered = [u for u in image_urls if u in url_set]

    logger.info(
        f"filter_manga_images: {len(ordered)}/{len(image_urls)} imágenes "
        f"pasan el filtro (min {min_dimension}px)"
    )
    return ordered
