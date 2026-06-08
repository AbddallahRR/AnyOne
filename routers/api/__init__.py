from fastapi import APIRouter

api_router = APIRouter(prefix='/api')

from . import content, downloads, library, scraper_configs, search, settings, updates  # noqa: F401
from .common import _invalidate_series_index  # noqa: F401
from .updates import _check_all_updates_core  # noqa: F401
