from .connection import get_conn


def update_queue_status(job_id: int, **kwargs) -> None:
    allowed = {'status', 'total_chapters', 'current_chapter', 'current_progress', 'error'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return
    conn = get_conn()
    set_clause = ', '.join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [job_id]
    with conn:
        conn.execute(f"UPDATE download_queue SET {set_clause} WHERE id = ?", params)


def queue_find_active(content_ref: str, chapter_id: str | None = None) -> tuple | None:
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


def queue_insert(content_ref: str, content_type: str, title: str,
                 chapter_id: str | None = None) -> int:
    conn = get_conn()
    with conn:
        cur = conn.execute(
            'INSERT INTO download_queue (content_ref, type, title, chapter_id, status) '
            "VALUES (?, ?, ?, ?, 'pending')",
            (content_ref, content_type, title, chapter_id)
        )
    return cur.lastrowid


def queue_get_status() -> tuple[list, list]:
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
