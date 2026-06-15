from .connection import get_conn


def get_source_settings() -> dict[str, bool]:
    conn = get_conn()
    rows = conn.execute('SELECT name, enabled FROM source_settings').fetchall()
    return {r['name']: bool(r['enabled']) for r in rows}


def update_source_settings(updates: dict[str, bool]) -> None:
    conn = get_conn()
    with conn:
        for name, enabled in updates.items():
            conn.execute(
                'UPDATE source_settings SET enabled = ? WHERE name = ?',
                (1 if enabled else 0, name)
            )


def get_enabled_source_names() -> list[str]:
    conn = get_conn()
    rows = conn.execute('SELECT name FROM source_settings WHERE enabled = 1').fetchall()
    return [r['name'] for r in rows]


def ensure_source_in_db(name: str, source_type: str) -> None:
    conn = get_conn()
    conn.execute(
        'INSERT OR IGNORE INTO source_settings (name, type, enabled) VALUES (?, ?, 1)',
        (name, source_type)
    )
