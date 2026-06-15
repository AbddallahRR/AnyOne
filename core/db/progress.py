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
            'INSERT OR REPLACE INTO user_progress (content_id, chapter, progress) VALUES (?, ?, ?)',
            (content_ref, chapter, progress)
        )
