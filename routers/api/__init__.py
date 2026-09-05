from fastapi import APIRouter

api_router = APIRouter(prefix='/api')

from . import content, downloads, library, media, progress, schedule, scraper_configs, scraper_tester, search, settings, updates, watched  # noqa: F401
from .common import _invalidate_series_index  # noqa: F401
from .updates import _check_all_updates_core, _check_all_updates_core_for_ref  # noqa: F401
