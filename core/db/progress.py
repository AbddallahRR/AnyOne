from .connection import get_conn


def get_progress(content_ref: str) -> tuple[str, str]:
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
            'INSERT INTO user_progress (content_id, chapter, progress, updated_at) VALUES (?, ?, ?, datetime(\'now\'))'
            ' ON CONFLICT(content_id) DO UPDATE SET chapter=excluded.chapter, progress=excluded.progress, updated_at=excluded.updated_at',
            (content_ref, chapter, progress)
        )


def get_recent_progress(limit: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        'SELECT content_id, chapter, progress '
        'FROM user_progress '
        'WHERE content_id LIKE ? '
        'ORDER BY updated_at DESC LIMIT ?',
        ('local:%', limit)
    ).fetchall()
    return [{'content_ref': r[0], 'chapter': r[1], 'progress': r[2]} for r in rows]
