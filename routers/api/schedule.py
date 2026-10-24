import logging

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

from core.database import (
    delete_series_schedule,
    get_all_schedules,
    get_series_schedule,
    set_series_schedule,
    set_series_status,
)
from core.utils import scan_downloaded_series

from . import api_router
from .common import _resolve_series_title

logger = logging.getLogger(__name__)


def _resolve_title(content_ref: str) -> str:
    if content_ref.startswith('local:'):
        folder = content_ref[6:]
        items = scan_downloaded_series()
        for item in items:
            if item['id'] == folder:
                return item.get('title', folder)
        return folder.replace('_', ' ').title()

    parts = content_ref.split(':', 1)
    if len(parts) == 2:
        return _resolve_series_title(parts[0], parts[1])
    return content_ref


@api_router.get('/schedule')
def api_get_all_schedules():
    schedules = get_all_schedules()
    result = []
    for s in schedules:
        title = _resolve_title(s['content_ref'])
        result.append({**s, 'title': title})
    return result


@api_router.get('/schedule/{content_ref:path}')
def api_get_schedule(content_ref: str):
    schedule = get_series_schedule(content_ref)
    if not schedule:
        return None
    title = _resolve_title(content_ref)
    return {**schedule, 'title': title}


class ScheduleRequest(BaseModel):
    content_ref: str = ''
    day_of_week: int = 0

    @field_validator('day_of_week')
    @classmethod
    def _valid_day(cls, v: int) -> int:
        if not (0 <= v <= 6):
            raise ValueError(f"Día inválido: {v}. Debe ser 0 (Lun) a 6 (Dom)")
        return v


@api_router.post('/schedule')
def api_set_schedule(data: ScheduleRequest):
    if not data.content_ref:
        raise HTTPException(status_code=400, detail='Falta content_ref')
    # check_hour is unused 迁移: el scheduler arranca a las 8 AM y reintenta cada 30 min
    set_series_schedule(data.content_ref, data.day_of_week, 0)
    set_series_status(data.content_ref, 'watching')
    title = _resolve_title(data.content_ref)
    return {
        'content_ref': data.content_ref,
        'day_of_week': data.day_of_week,
        'title': title,
    }


@api_router.delete('/schedule/{content_ref:path}')
def api_delete_schedule(content_ref: str):
    delete_series_schedule(content_ref)
    return {'deleted': content_ref}
