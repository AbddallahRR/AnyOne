import time

from .connection import get_conn

_enabled_names_cache: list[str] | None = None
_enabled_names_cache_time: float = 0.0
_ENABLED_NAMES_TTL = 30.0


def get_source_settings() -> dict[str, bool]:
    conn = get_conn()
    rows = conn.execute('SELECT name, enabled FROM source_settings').fetchall()
    return {r['name']: bool(r['enabled']) for r in rows}


def update_source_settings(updates: dict[str, bool]) -> None:
    global _enabled_names_cache
    conn = get_conn()
    with conn:
        for name, enabled in updates.items():
            conn.execute(
                'UPDATE source_settings SET enabled = ? WHERE name = ?',
                (1 if enabled else 0, name)
            )
    _enabled_names_cache = None


def get_enabled_source_names() -> list[str]:
    global _enabled_names_cache, _enabled_names_cache_time
    now = time.time()
    if _enabled_names_cache is not None and now - _enabled_names_cache_time < _ENABLED_NAMES_TTL:
        return _enabled_names_cache
    conn = get_conn()
    rows = conn.execute('SELECT name FROM source_settings WHERE enabled = 1').fetchall()
    _enabled_names_cache = [r['name'] for r in rows]
    _enabled_names_cache_time = now
    return _enabled_names_cache


def ensure_source_in_db(name: str, source_type: str) -> None:
    global _enabled_names_cache
    conn = get_conn()
    conn.execute(
        'INSERT OR IGNORE INTO source_settings (name, type, enabled) VALUES (?, ?, 1)',
        (name, source_type)
    )
    _enabled_names_cache = None
