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
        "WHERE content_id >= 'local:' AND content_id < 'local;' "
        'ORDER BY updated_at DESC LIMIT ?',
        (limit,)
    ).fetchall()
    return [{'content_ref': r[0], 'chapter': r[1], 'progress': r[2]} for r in rows]


def get_recent_remote_progress(content_type: str) -> list[dict]:
    """Últimas series REMOTAS con progreso (NO local), para la fila
    'Continuar viendo' del panel de búsqueda. Sin límite a propósito: a
    diferencia de la bomba de la biblioteca (10 items), aquí la serie
    completa de lo visto remoto. Los datos de título/portada salen de la
    tabla content (se rellena al abrir los detalles de la serie)."""
    conn = get_conn()
    rows = conn.execute(
        'SELECT c.source, c.content_id, up.chapter, up.progress, c.title, c.cover '
        'FROM user_progress up '
        'JOIN content c ON c.id = up.content_id '
        "WHERE c.type = ? AND up.content_id NOT LIKE 'local:%' "
        'ORDER BY up.updated_at DESC',
        (content_type,)
    ).fetchall()
    return [
        {
            'source': r[0],
            'content_id': r[1],
            'chapter': r[2],
            'progress': r[3],
            'title': r[4],
            'cover': r[5],
        }
        for r in rows
    ]
