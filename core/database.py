from core.db.connection import cleanup_download_queue, get_conn, init_db
from core.db.content import delete_content_from_db, get_content_ref, save_content_to_db
from core.db.downloads import update_queue_status
from core.db.library import (
    clear_series_updates,
    get_all_series_statuses,
    get_last_checked,
    get_series_status,
    get_series_to_check,
    get_series_with_updates,
    mark_series_checked,
    set_series_status,
    set_series_updates,
)
from core.db.progress import get_progress, save_progress
from core.db.settings import (
    ensure_source_in_db,
    get_enabled_source_names,
    get_source_settings,
    update_source_settings,
)
from core.db.watched import (
    delete_watched_chapter,
    delete_watched_chapters_batch,
    get_watched_chapters,
    is_chapter_watched,
    mark_chapter_as_watched,
)
