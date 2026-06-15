import json
import logging
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import HTTPException

from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR
from core.database import get_conn
from core.chapter_utils import chapter_float_key, normalize_chapter_number
from core.models import chapter_to_filename, parse_chapter_from_filename
from core.utils import _normalize_path_name

logger = logging.getLogger(__name__)


_series_index: dict[str, dict[str, Path]] = {}
_series_index_lock = threading.Lock()


def _read_series_info(cand_dir: Path) -> tuple[str | None, Path | None]:
    """Lee series_info.json de un directorio y devuelve (content_id, dir_path) o (None, None)."""
    info_path = cand_dir / 'series_info.json'
    if not info_path.exists():
        return None, None
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            info = json.load(f)
        cid = info.get('content_id')
        if cid:
            return cid, cand_dir
    except Exception as exc:
        logger.warning("Error leyendo %s: %s", info_path, exc)
    return None, None


def _build_series_index(base_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not base_dir.exists():
        return index

    dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    if not dirs:
        return index

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_read_series_info, d): d for d in dirs}
        for future in as_completed(futures):
            try:
                cid, cand_dir = future.result()
                if cid and cand_dir:
                    index[cid] = cand_dir
            except Exception:
                pass
    return index


def _get_series_index(base_dir: Path) -> dict[str, Path]:
    key = str(base_dir)
    with _series_index_lock:
        if key not in _series_index:
            _series_index[key] = _build_series_index(base_dir)
        return _series_index[key]


def _invalidate_series_index(base_dir: Path | None = None) -> None:
    with _series_index_lock:
        if base_dir is None:
            _series_index.clear()
        else:
            _series_index.pop(str(base_dir), None)


def _safe_path(base: str, untrusted: str) -> Path | None:
    try:
        resolved = Path(base, untrusted).resolve()
        if resolved.is_relative_to(Path(base).resolve()):
            return resolved
    except Exception:
        pass
    return None


def _base_folder(content_type: str) -> str:
    return ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR


def _require_local(content_ref: str):
    if not content_ref.startswith('local:'):
        raise HTTPException(status_code=400, detail='Solo funciona con contenido local')


def _queue_find_active(content_ref: str, chapter_id: str | None = None) -> tuple | None:
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
    conn = get_conn()
    with conn:
        cur = conn.execute(
            'INSERT INTO download_queue (content_ref, type, title, chapter_id, status) '
            "VALUES (?, ?, ?, ?, 'pending')",
            (content_ref, content_type, title, chapter_id)
        )
    return cur.lastrowid


def _queue_get_status() -> tuple[list, list]:
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


def _find_local_serie_dir(base_dir: Path, content_id: str) -> Path | None:
    index = _get_series_index(base_dir)
    if content_id in index:
        candidate = index[content_id]
        if candidate.exists():
            return candidate
        _invalidate_series_index(base_dir)
        index = _get_series_index(base_dir)
        if content_id in index:
            return index[content_id]
    norm_id = _normalize_path_name(content_id)
    if base_dir.exists():
        for cand_dir in base_dir.iterdir():
            if cand_dir.is_dir() and _normalize_path_name(cand_dir.name) == norm_id:
                return cand_dir
    return None


def _local_chapters_anime(serie_dir: Path) -> list[dict]:
    chapters = []
    for f in sorted(serie_dir.glob("*.mp4")):
        num = parse_chapter_from_filename(f.stem)
        if num:
            chapters.append({'number': num, 'id': num})
    return chapters


def _local_chapters_manga(serie_dir: Path) -> list[dict]:
    chapters = []
    for d in sorted(d for d in serie_dir.iterdir() if d.is_dir() and d.name.startswith('cap_')):
        m = re.search(r'cap_([\d._]+)', d.name)
        if m:
            num = normalize_chapter_number(m.group(1).replace('_', '.'))
            chapters.append({'number': num, 'id': num})
    return chapters


def _delete_chapter_files(serie_path: Path, content_type: str, chapter: str) -> None:
    chap_str = chapter_to_filename(chapter, padding=3 if content_type == 'anime' else 4)
    if content_type == 'anime':
        for f in serie_path.glob(f"*_{chap_str}.mp4"):
            f.unlink()
    else:
        cap_dir = serie_path / f"cap_{chap_str}"
        if cap_dir.exists() and cap_dir.is_dir():
            shutil.rmtree(cap_dir)


def _resolve_series_title(source_name: str, content_id: str) -> str:
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
