from fastapi import Depends, HTTPException
from fastapi.requests import Request

from core.sources import get_source as _get_source
from core.sources import get_enabled_source_names, SOURCES


async def get_source(content_type: str, source: str):
    src = _get_source(content_type, source)
    if not src:
        raise HTTPException(status_code=404, detail='Fuente no encontrada')
    enabled = get_enabled_source_names()
    if source not in enabled:
        raise HTTPException(status_code=400, detail='Fuente desactivada en configuración')
    return src
