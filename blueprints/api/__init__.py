from flask import Blueprint

api_bp = Blueprint('api', __name__, url_prefix='/api')

from . import search, content, library, downloads, updates  # noqa: E402, F401
from .updates import _check_all_updates_core  # noqa: E402, F401
