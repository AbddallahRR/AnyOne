import logging
import os
import shutil
import sqlite3
import threading
import time

from core.settings import settings

logger = logging.getLogger(__name__)

_local = threading.local()
SCHEMA_VERSION = 12


def execute_with_retry(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    for attempt in range(6):
        try:
            conn = get_conn()
            with conn:
                return conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            if 'locked' in str(exc):
                if attempt < 5:
                    logger.debug("DB bloqueada, reintento %d/5...", attempt + 1)
                    time.sleep(2 ** attempt)
                    _local.conn = None
                    continue
                logger.warning("DB persistentemente bloqueada tras 5 reintentos")
                raise
            raise


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'conn') or _local.conn is None:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(settings.db_path), check_same_thread=False, timeout=60)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-16000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=60000")
        _local.conn = conn
    return _local.conn


def _get_schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return row[0] if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version VALUES (?)", (version,))


def _run_migrations(conn: sqlite3.Connection, current: int) -> None:
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

    if current < 4:
        logger.info("Migracion 4: columna last_checked_at en series_status")
        existing = [r[1] for r in conn.execute("PRAGMA table_info(series_status)")]
        if 'last_checked_at' not in existing:
            conn.execute(
                "ALTER TABLE series_status ADD COLUMN last_checked_at TIMESTAMP"
            )

    if current < 5:
        logger.info("Migracion 5: columna new_chapters_found en series_status")
        existing = [r[1] for r in conn.execute("PRAGMA table_info(series_status)")]
        if 'new_chapters_found' not in existing:
            conn.execute(
                "ALTER TABLE series_status ADD COLUMN new_chapters_found TEXT DEFAULT ''"
            )

    if current < 6:
        logger.info("Migracion 6: tabla source_settings")
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS source_settings (
                name    TEXT PRIMARY KEY,
                type    TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            INSERT OR IGNORE INTO source_settings (name, type, enabled) VALUES
                ('jkanime',   'anime', 1),
                ('nartag',    'manga', 1),
                ('manhwaweb', 'manga', 1),
                ('ikigai',    'manga', 1);
        ''')

    if current < 7:
        logger.info("Migracion 7: tabla scraper_configs")
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS scraper_configs (
                name        TEXT PRIMARY KEY,
                type        TEXT NOT NULL,
                label       TEXT NOT NULL,
                base_url    TEXT NOT NULL DEFAULT '',
                built_in    INTEGER NOT NULL DEFAULT 0,
                enabled     INTEGER NOT NULL DEFAULT 1,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            INSERT OR IGNORE INTO scraper_configs (name, type, label, base_url, built_in, enabled, config_json, created_at, updated_at)
            VALUES
                ('jkanime', 'anime', 'JKanime', 'https://jkanime.net', 1, 1, '{}', strftime('%s','now'), strftime('%s','now')),
                ('nartag', 'manga', 'Nartag', 'https://nartag.com', 1, 1, '{}', strftime('%s','now'), strftime('%s','now')),
                ('manhwaweb', 'manga', 'ManhwaWeb', 'https://www.manhwaweb.com', 1, 1, '{}', strftime('%s','now'), strftime('%s','now')),
                ('ikigai', 'manga', 'Ikigai', 'https://visorikigai.yomod.xyz', 1, 1, '{}', strftime('%s','now'), strftime('%s','now'));
        ''')

    if current < 8:
        logger.info("Migracion 8: watched_chapters.chapter_number TEXT para soportar decimales")
        existing = [r[1] for r in conn.execute("PRAGMA table_info(watched_chapters)")]
        if existing and existing[2] == 'INTEGER':
            conn.executescript('''
                CREATE TABLE watched_chapters_new (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id     TEXT NOT NULL,
                    chapter_number TEXT NOT NULL,
                    watched_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(content_id, chapter_number)
                );
                INSERT INTO watched_chapters_new (id, content_id, chapter_number, watched_at)
                    SELECT id, content_id, CAST(chapter_number AS TEXT), watched_at
                    FROM watched_chapters;
                DROP TABLE watched_chapters;
                ALTER TABLE watched_chapters_new RENAME TO watched_chapters;
                CREATE INDEX IF NOT EXISTS idx_watched_cid ON watched_chapters(content_id);
            ''')

    if current < 9:
        logger.info("Migracion 9: indices faltantes para rendimiento")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_content_ref_status ON download_queue(content_ref, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_status_created ON download_queue(status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_status_check ON series_status(status, last_checked_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_status_updates ON series_status(new_chapters_found)")

    if current < 10:
        logger.info("Migracion 10: columna updated_at en user_progress")
        existing = [r[1] for r in conn.execute("PRAGMA table_info(user_progress)")]
        if 'updated_at' not in existing:
            conn.execute(
                "ALTER TABLE user_progress ADD COLUMN updated_at TIMESTAMP"
            )

    # Fix filas existentes con updated_at NULL (migracion 10 incompleta)
    conn.execute(
        "UPDATE user_progress SET updated_at = datetime('now') WHERE updated_at IS NULL"
    )

    if current < 11:
        logger.info("Migracion 11: indice compuesto en user_progress para get_recent_progress")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_progress_updated "
            "ON user_progress(content_id, updated_at DESC)"
        )

    if current < 12:
        logger.info("Migracion 12: eliminar fuentes obsoletas nartag y manhwaweb")
        conn.execute("DELETE FROM scraper_configs WHERE name IN ('nartag', 'manhwaweb')")
        conn.execute("DELETE FROM source_settings WHERE name IN ('nartag', 'manhwaweb')")


def init_db() -> None:
    for attempt in range(6):
        try:
            conn = get_conn()
            with conn:
                current = _get_schema_version(conn)
                if current < SCHEMA_VERSION:
                    _run_migrations(conn, current)
                    _set_schema_version(conn, SCHEMA_VERSION)
                    logger.info(f"Esquema actualizado a version {SCHEMA_VERSION}")
                else:
                    logger.debug("Esquema ya actualizado, sin migraciones pendientes")
            return
        except sqlite3.OperationalError as exc:
            if 'locked' in str(exc):
                if attempt < 5:
                    logger.warning(f"init_db: DB bloqueada, reintento {attempt+1}/5...")
                    time.sleep(2 ** attempt)
                    _local.conn = None
                    continue
                logger.warning(
                    "init_db: DB persistentemente bloqueada, saltando migraciones. "
                    "Si el esquema cambió, reiniciar cuando no haya otro proceso activo."
                )
                return
            raise


def cleanup_download_queue() -> None:
    conn = None
    for attempt in range(6):
        try:
            conn = get_conn()
            rows = conn.execute(
                'SELECT id, content_ref, type, title, current_chapter, chapter_id '
                'FROM download_queue WHERE status = "downloading"'
            ).fetchall()
            break
        except sqlite3.OperationalError as exc:
            if 'locked' in str(exc):
                if attempt < 5:
                    logger.warning(f"cleanup_download_queue: DB bloqueada, reintento {attempt+1}/5...")
                    time.sleep(2 ** attempt)
                    _local.conn = None
                    continue
                logger.warning("cleanup_download_queue: DB persistentemente bloqueada, omitiendo.")
                return
            raise

    if conn is None:
        return

    for row in rows:
        job_id, content_ref, content_type, title, current_chapter, chapter_id = row
        from core.utils import normalize_title
        try:
            base_folder = str(settings.anime_download_dir) if content_type == 'anime' else str(settings.manga_download_dir)
            safe_title  = normalize_title(title)
            series_folder = os.path.join(base_folder, safe_title)

            cap_num: str | None = None
            if chapter_id:
                raw = chapter_id.split('-')[-1] if '-' in chapter_id else chapter_id
                if raw.replace('.', '', 1).isdigit():
                    cap_num = raw
            elif current_chapter:
                cap_num = str(current_chapter)

            if cap_num and float(cap_num) > 0:
                if content_type == 'anime':
                    filepath = os.path.join(series_folder, f"{safe_title}_{cap_num}.mp4")
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.info(f"[CLEANUP] Archivo parcial eliminado: {filepath}")
                else:
                    filepath = os.path.join(series_folder, f"cap_{cap_num}")
                    if os.path.exists(filepath):
                        shutil.rmtree(filepath)
                        logger.info(f"[CLEANUP] Carpeta parcial eliminada: {filepath}")
        except Exception as exc:
            logger.exception(f"[CLEANUP] Error limpiando job {job_id}: {exc}")

    try:
        with conn:
            conn.execute(
                "UPDATE download_queue SET status='failed', error='Interrumpido por reinicio del servidor' "
                "WHERE status IN ('pending', 'downloading')"
            )
        logger.info("[CLEANUP] Cola de descarga limpiada")
    except sqlite3.OperationalError as exc:
        logger.warning(f"[CLEANUP] No se pudo limpiar la cola: {exc}")
