import logging

from .connection import execute_with_retry, get_conn

logger = logging.getLogger(__name__)


def set_series_schedule(content_ref: str, day_of_week: int, check_hour: int) -> None:
    if not (0 <= day_of_week <= 6):
        raise ValueError(f"Día inválido: {day_of_week}. Debe ser 0 (Lun) a 6 (Dom)")
    if not (0 <= check_hour <= 23):
        raise ValueError(f"Hora inválida: {check_hour}. Debe ser 0 a 23")

    execute_with_retry(
        '''INSERT INTO series_schedule (content_ref, day_of_week, check_hour, updated_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(content_ref) DO UPDATE SET
               day_of_week = excluded.day_of_week,
               check_hour  = excluded.check_hour,
               updated_at  = excluded.updated_at''',
        (content_ref, day_of_week, check_hour)
    )


def get_series_schedule(content_ref: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        'SELECT content_ref, day_of_week, check_hour FROM series_schedule WHERE content_ref = ?',
        (content_ref,)
    ).fetchone()
    if not row:
        return None
    return {
        'content_ref': row[0],
        'day_of_week': row[1],
        'check_hour': row[2],
    }


def get_all_schedules() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        'SELECT content_ref, day_of_week, check_hour FROM series_schedule'
    ).fetchall()
    return [
        {'content_ref': r[0], 'day_of_week': r[1], 'check_hour': r[2]}
        for r in rows
    ]


def get_schedules_for_day(day_of_week: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        '''SELECT s.content_ref, s.day_of_week, s.check_hour
           FROM series_schedule s
           JOIN series_status st ON st.content_ref = s.content_ref
           WHERE s.day_of_week = ? AND st.status = 'watching' ''',
        (day_of_week,)
    ).fetchall()
    return [
        {'content_ref': r[0], 'day_of_week': r[1], 'check_hour': r[2]}
        for r in rows
    ]


def delete_series_schedule(content_ref: str) -> None:
    execute_with_retry(
        'DELETE FROM series_schedule WHERE content_ref = ?',
        (content_ref,)
    )
