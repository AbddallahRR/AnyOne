from .connection import get_conn


def save_content_to_db(content_type: str, source: str, content_id: str,
                        title: str, cover: str) -> None:
    ref  = f"{source}:{content_id}"
    conn = get_conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO content (id, type, source, content_id, title, cover) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (ref, content_type, source, content_id, title, cover)
        )


def get_content_ref(source: str, content_id: str) -> str:
    return f"{source}:{content_id}"
