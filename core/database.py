#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import sqlite3
import logging
import threading

from config import DB_PATH, ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR
from core.utils import normalize_title

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool (una conexión por hilo, reutilizada)
# ---------------------------------------------------------------------------

_local = threading.local()

def get_conn() -> sqlite3.Connection:
    """Devuelve la conexión SQLite del hilo actual, creándola si no existe."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row          # acceso por nombre de columna
        conn.execute("PRAGMA journal_mode=WAL") # lecturas y escrituras no se bloquean entre sí
        conn.execute("PRAGMA synchronous=NORMAL")  # más rápido, igual de seguro que FULL
        conn.execute("PRAGMA cache_size=-32000")   # 32 MB de caché en memoria
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


# ---------------------------------------------------------------------------
# Migraciones versionadas
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 3  # incrementar al agregar una migración nueva

def _get_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0

def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version VALUES (?)", (version,))

def _run_migrations(conn: sqlite3.Connection, current: int) -> None:
    """Aplica solo las migraciones pendientes según la versión actual."""

    if current < 1:
        logger.info("Migracion 1: creando tablas base")
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS content (
                id         TEXT PRIMARY KEY,
                type       TEXT NOT NULL,
                source     TEXT NOT NULL,
                content_id TEXT NOT NULL,
                title      TEXT NOT NULL,
                cover      TEXT
            );
            CREATE TABLE IF NOT EXISTS user_progress (
                content_id TEXT PRIMARY KEY,
                chapter    TEXT NOT NULL,
                progress   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS download_queue (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                content_ref      TEXT NOT NULL,
                type             TEXT NOT NULL,
                title            TEXT NOT NULL,
                chapter_id       TEXT,
                status           TEXT DEFAULT 'pending',
                total_chapters   INTEGER DEFAULT 0,
                current_chapter  INTEGER DEFAULT 0,
                current_progress INTEGER DEFAULT 0,
                error            TEXT,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS watched_chapters (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id     TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                watched_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(content_id, chapter_number)
            );
            CREATE INDEX IF NOT EXISTS idx_queue_status  ON download_queue(status);
            CREATE INDEX IF NOT EXISTS idx_content_type  ON content(type);
            CREATE INDEX IF NOT EXISTS idx_watched_cid   ON watched_chapters(content_id);
        ''')

    if current < 2:
        logger.info("Migracion 2: columnas chapter_id / content_ref (compatibilidad)")
        existing = [r[1] for r in conn.execute("PRAGMA table_info(download_queue)")]
        if 'chapter_id' not in existing:
            conn.execute("ALTER TABLE download_queue ADD COLUMN chapter_id TEXT")
        if 'content_ref' not in existing:
            conn.execute("ALTER TABLE download_queue ADD COLUMN content_ref TEXT")

    if current < 3:
        logger.info("Migracion 3: tabla series_status (etiquetas de biblioteca)")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS series_status (
                content_ref TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'pending',
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_series_status ON series_status(status)"
        )


# ---------------------------------------------------------------------------
# Inicialización pública
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Crea / migra el esquema. Llamar una sola vez desde create_app()."""
    conn = get_conn()
    with conn:                              # transacción única para todo el esquema
        current = _get_schema_version(conn)
        if current < SCHEMA_VERSION:
            _run_migrations(conn, current)
            _set_schema_version(conn, SCHEMA_VERSION)
            logger.info(f"Esquema actualizado a version {SCHEMA_VERSION}")
        else:
            logger.debug("Esquema ya actualizado, sin migraciones pendientes")


# ---------------------------------------------------------------------------
# Limpieza al arrancar (lógica de archivos separada del acceso a DB)
# ---------------------------------------------------------------------------

def cleanup_download_queue() -> None:
    """
    Al arrancar: elimina archivos parciales de jobs interrumpidos y los marca
    como 'failed'. La lógica de rutas vive aquí, no en database.py puro, pero
    se mantiene en este módulo para no romper la API pública existente.
    """
    conn = get_conn()

    # Jobs que estaban descargando cuando el servidor se cayó
    rows = conn.execute(
        'SELECT id, content_ref, type, title, current_chapter, chapter_id '
        'FROM download_queue WHERE status = "downloading"'
    ).fetchall()

    for row in rows:
        job_id, content_ref, content_type, title, current_chapter, chapter_id = row
        try:
            base_folder = ANIME_DOWNLOAD_DIR if content_type == 'anime' else MANGA_DOWNLOAD_DIR
            safe_title  = normalize_title(title)
            series_folder = os.path.join(base_folder, safe_title)

            cap_num: int | None = None
            if chapter_id:
                raw = chapter_id.split('-')[-1] if '-' in chapter_id else chapter_id
                cap_num = int(raw) if raw.isdigit() else None
            elif current_chapter:
                cap_num = int(current_chapter)

            if cap_num and cap_num > 0:
                if content_type == 'anime':
                    filepath = os.path.join(series_folder, f"{safe_title}_{cap_num:03d}.mp4")
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.info(f"[CLEANUP] Archivo parcial eliminado: {filepath}")
                else:
                    filepath = os.path.join(series_folder, f"cap_{cap_num:04d}")
                    if os.path.exists(filepath):
                        shutil.rmtree(filepath)
                        logger.info(f"[CLEANUP] Carpeta parcial eliminada: {filepath}")
        except Exception as exc:
            logger.error(f"[CLEANUP] Error limpiando job {job_id}: {exc}")

    with conn:
        conn.execute(
            "UPDATE download_queue SET status='failed', error='Interrumpido por reinicio del servidor' "
            "WHERE status IN ('pending', 'downloading')"
        )
    logger.info("[CLEANUP] Cola de descarga limpiada")


# ---------------------------------------------------------------------------
# Operaciones sobre content
# ---------------------------------------------------------------------------

def save_content_to_db(content_type: str, source: str, content_id: str,
                        title: str, cover: str) -> None:
    """Guarda o actualiza un contenido en la tabla content."""
    ref  = f"{source}:{content_id}"
    conn = get_conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO content (id, type, source, content_id, title, cover) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (ref, content_type, source, content_id, title, cover)
        )


def get_content_ref(content_type: str, source: str, content_id: str) -> str:
    """Genera la clave compuesta para referenciar un contenido."""
    # content_type no se usa, se mantiene por compatibilidad
    return f"{source}:{content_id}"


# ---------------------------------------------------------------------------
# Progreso del usuario
# ---------------------------------------------------------------------------

def get_progress(content_ref: str) -> tuple[str, str]:
    """Devuelve (chapter, progress). Por defecto ('1', '0')."""
    conn = get_conn()
    row = conn.execute(
        'SELECT chapter, progress FROM user_progress WHERE content_id = ?',
        (content_ref,)
    ).fetchone()
    return (row[0], row[1]) if row else ('1', '0')


def save_progress(content_ref: str, chapter: str, progress: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO user_progress (content_id, chapter, progress) VALUES (?, ?, ?)',
            (content_ref, chapter, progress)
        )


# ---------------------------------------------------------------------------
# Cola de descarga
# ---------------------------------------------------------------------------

def update_queue_status(job_id: int, **kwargs) -> None:
    """Actualiza campos permitidos de un job en la cola."""
    allowed = {'status', 'total_chapters', 'current_chapter', 'current_progress', 'error'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    logger.debug(f"update_queue_status job={job_id} {updates}")
    conn = get_conn()
    set_clause = ', '.join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [job_id]
    with conn:
        conn.execute(f"UPDATE download_queue SET {set_clause} WHERE id = ?", params)



# ---------------------------------------------------------------------------
# Etiquetas de biblioteca (watching / completed / pending)
# ---------------------------------------------------------------------------

_VALID_STATUSES = {'watching', 'completed', 'pending', 'none'}

def set_series_status(content_ref: str, status: str) -> None:
    """Guarda o actualiza la etiqueta de una serie. 'none' elimina la fila."""
    conn = get_conn()
    with conn:
        if status == 'none':
            conn.execute('DELETE FROM series_status WHERE content_ref = ?', (content_ref,))
        else:
            conn.execute(
                '''INSERT INTO series_status (content_ref, status, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(content_ref) DO UPDATE SET
                       status = excluded.status,
                       updated_at = excluded.updated_at''',
                (content_ref, status)
            )

def get_series_status(content_ref: str) -> str:
    """Devuelve la etiqueta de una serie, o 'none' si no tiene."""
    conn = get_conn()
    row = conn.execute(
        'SELECT status FROM series_status WHERE content_ref = ?', (content_ref,)
    ).fetchone()
    return row[0] if row else 'none'

def get_all_series_statuses() -> dict[str, str]:
    """Devuelve un dict content_ref -> status para todas las series etiquetadas."""
    conn = get_conn()
    rows = conn.execute('SELECT content_ref, status FROM series_status').fetchall()
    return {r[0]: r[1] for r in rows}

# ---------------------------------------------------------------------------
# Capítulos vistos
# ---------------------------------------------------------------------------

def mark_chapter_as_watched(content_ref: str, chapter_number: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            'INSERT OR IGNORE INTO watched_chapters (content_id, chapter_number) VALUES (?, ?)',
            (content_ref, chapter_number)
        )


def is_chapter_watched(content_ref: str, chapter_number: int) -> bool:
    conn = get_conn()
    return conn.execute(
        'SELECT 1 FROM watched_chapters WHERE content_id = ? AND chapter_number = ?',
        (content_ref, chapter_number)
    ).fetchone() is not None


def get_watched_chapters(content_ref: str) -> list[int]:
    conn = get_conn()
    rows = conn.execute(
        'SELECT chapter_number FROM watched_chapters WHERE content_id = ?',
        (content_ref,)
    ).fetchall()
    return [r[0] for r in rows]


def delete_watched_chapter(content_ref: str, chapter_number: int) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            'DELETE FROM watched_chapters WHERE content_id = ? AND chapter_number = ?',
            (content_ref, chapter_number)
        )