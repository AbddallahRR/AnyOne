from .connection import get_conn


def mark_chapter_as_watched(content_ref: str, chapter_number: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            'INSERT OR IGNORE INTO watched_chapters (content_id, chapter_number) VALUES (?, ?)',
            (content_ref, chapter_number)
        )


def is_chapter_watched(content_ref: str, chapter_number: str) -> bool:
    conn = get_conn()
    return conn.execute(
        'SELECT 1 FROM watched_chapters WHERE content_id = ? AND chapter_number = ?',
        (content_ref, chapter_number)
    ).fetchone() is not None


def get_watched_chapters(content_ref: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        'SELECT chapter_number FROM watched_chapters WHERE content_id = ?',
        (content_ref,)
    ).fetchall()
    return [str(r[0]) for r in rows]


def delete_watched_chapter(content_ref: str, chapter_number: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            'DELETE FROM watched_chapters WHERE content_id = ? AND chapter_number = ?',
            (content_ref, chapter_number)
        )


def delete_watched_chapters_batch(content_ref: str, chapter_numbers: list[str]) -> None:
    if not chapter_numbers:
        return
    conn = get_conn()
    placeholders = ','.join('?' * len(chapter_numbers))
    with conn:
        conn.execute(
            f'DELETE FROM watched_chapters WHERE content_id = ? AND chapter_number IN ({placeholders})',
            [content_ref] + chapter_numbers
        )
