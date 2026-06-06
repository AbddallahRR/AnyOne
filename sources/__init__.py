import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

from core.models import Chapter, SearchResult, SeriesDetails


class BaseSource:
    """Clase base para todas las fuentes (anime y manga).

    Cada método tiene una versión sync (implementada por las subclases)
    y una versión async (wrapper por defecto que delega a la sync
    mediante un ThreadPoolExecutor acotado). Las subclases pueden
    sobreescribir la versión async para implementaciones nativamente async.
    """

    _executor = ThreadPoolExecutor(max_workers=4)

    async def _run_in_executor(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, lambda: func(*args, **kwargs))

    def search_sync(self, query: str) -> list[SearchResult]:
        raise NotImplementedError

    async def search(self, query: str) -> list[SearchResult]:
        return await self._run_in_executor(self.search_sync, query)

    def get_details_sync(self, content_id: str) -> SeriesDetails:
        raise NotImplementedError

    async def get_details(self, content_id: str) -> SeriesDetails:
        return await self._run_in_executor(self.get_details_sync, content_id)

    def get_chapters_sync(self, content_id: str) -> list[Chapter]:
        raise NotImplementedError

    async def get_chapters(self, content_id: str) -> list[Chapter]:
        return await self._run_in_executor(self.get_chapters_sync, content_id)

    def download_chapter_sync(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        raise NotImplementedError

    async def download_chapter(self, content_id: str, chapter_id: str, dest_folder: str) -> str:
        return await self._run_in_executor(self.download_chapter_sync, content_id, chapter_id, dest_folder)

    def get_stream_url_sync(self, content_id: str, chapter_id: str) -> str | None:
        return None

    async def get_stream_url(self, content_id: str, chapter_id: str) -> str | None:
        return await self._run_in_executor(self.get_stream_url_sync, content_id, chapter_id)

    def warm_cache_sync(self) -> None:
        pass

    async def warm_cache(self) -> None:
        return await self._run_in_executor(self.warm_cache_sync)
