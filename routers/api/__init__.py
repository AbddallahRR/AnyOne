from fastapi import APIRouter

api_router = APIRouter(prefix='/api')

from . import content, downloads, library, media, progress, realtime, schedule, scraper_configs, scraper_tester, search, settings, updates, watched  # noqa: F401
