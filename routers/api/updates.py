import asyncio

from fastapi import HTTPException

from core.updates import check_all_updates, check_series

from . import api_router


@api_router.post('/library/check-updates/{content_ref:path}')
async def api_check_updates(content_ref: str):
    result = await asyncio.to_thread(check_series, content_ref)
    if result.get('error'):
        raise HTTPException(status_code=500, detail='Error interno al comprobar actualizaciones')
    return result


@api_router.post('/library/check-all-updates')
async def api_check_all_updates():
    return await asyncio.to_thread(check_all_updates)
