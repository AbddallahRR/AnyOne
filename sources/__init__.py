import asyncio
import functools

from core.models import Chapter, SearchResult, SeriesDetails


def _run_sync(f):
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(f, *args, **kwargs)
    return wrapper


class BaseSource:
    """Clase base para todas las fuentes (anime y manga).

    Cada método tiene una versión sync (implementada por las subclases)
    y una versión async (wrapper por defecto que delega a la sync
    mediante asyncio.to_thread). Las subclases pueden sobreescribir
    la versión async para implementaciones nativamente async.
    """

    def search_sync(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    async def search(self, query: str) -> list[SearchResult]:
        return await asyncio.to_thread(self.search_sync, query)

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        raise NotImplementedError

    async def get_details(self, content_id: str) -> SeriesDetails:
        return await asyncio.to_thread(self.get_details_sync, content_id)

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        raise NotImplementedError

    async def get_chapters(self, content_id: str) -> list[Chapter]:
        return await asyncio.to_thread(self.get_chapters_sync, content_id)

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        raise NotImplementedError

    async def download_chapter(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        return await asyncio.to_thread(self.download_chapter_sync, content_id, chapter_id, dest_folder)

    def get_stream_url_sync(self, content_id: str, chapter_id: str) -> str | None:
        return None

    async def get_stream_url(self, content_id: str, chapter_id: str) -> str | None:
        return await asyncio.to_thread(self.get_stream_url_sync, content_id, chapter_id)

    def warm_cache_sync(self) -> None:
        pass

    async def warm_cache(self) -> None:
        return await asyncio.to_thread(self.warm_cache_sync)
