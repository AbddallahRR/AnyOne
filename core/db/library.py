import json
import logging

from .connection import execute_with_retry, get_conn

logger = logging.getLogger(__name__)

_VALID_STATUSES = {'watching', 'completed', 'pending', 'none'}


def set_series_status(content_ref: str, status: str) -> None:
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
    conn = get_conn()
    row = conn.execute(
        'SELECT status FROM series_status WHERE content_ref = ?', (content_ref,)
    ).fetchone()
    return row[0] if row else 'none'


def get_all_series_statuses() -> dict[str, str]:
    conn = get_conn()
    rows = conn.execute('SELECT content_ref, status FROM series_status').fetchall()
    return {r[0]: r[1] for r in rows}


def get_series_to_check(min_interval_seconds: int = 86400) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT content_ref, status
        FROM series_status
        WHERE status IN ('watching', 'completed')
          AND (
            last_checked_at IS NULL
            OR last_checked_at <= datetime('now', ? || ' seconds')
          )
        """,
        (f"-{min_interval_seconds}",)
    ).fetchall()
    return [{'content_ref': r[0], 'status': r[1]} for r in rows]


def mark_series_checked(content_ref: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE series_status SET last_checked_at = CURRENT_TIMESTAMP "
            "WHERE content_ref = ?",
            (content_ref,)
        )


def get_last_checked(content_ref: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_checked_at FROM series_status WHERE content_ref = ?",
        (content_ref,)
    ).fetchone()
    return row[0] if row else None


def set_series_updates(content_ref: str, new_chapters: list[str]) -> None:
    conn = get_conn()
    value = json.dumps(new_chapters) if new_chapters else ''
    with conn:
        conn.execute(
            "UPDATE series_status SET new_chapters_found = ? WHERE content_ref = ?",
            (value, content_ref)
        )


def get_series_with_updates() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT content_ref, new_chapters_found FROM series_status "
        "WHERE new_chapters_found IS NOT NULL AND new_chapters_found != ''"
    ).fetchall()
    result = []
    for r in rows:
        try:
            chapters = json.loads(r[1])
            chapters = [str(c) for c in chapters]
            if chapters:
                result.append({'content_ref': r[0], 'new_chapters': chapters})
        except (json.JSONDecodeError, TypeError):
            pass
    return result


def clear_series_updates(content_ref: str) -> None:
    execute_with_retry(
        "UPDATE series_status SET new_chapters_found = '' WHERE content_ref = ?",
        (content_ref,)
    )


def clear_all_series_updates() -> None:
    execute_with_retry(
        "UPDATE series_status SET new_chapters_found = '' WHERE new_chapters_found != ''"
    )
