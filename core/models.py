from typing import Optional

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Fase 2: Modelos de dominio (contratos de fuentes)
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    id: str
    title: str
    cover: Optional[str] = None
    source: str = ''
    type: Optional[str] = None
    last_chapter: str = '1'
    progress: str = '0'


class SeriesDetails(BaseModel):
    title: str
    cover: Optional[str] = None
    synopsis: str = ''
    type: Optional[str] = None
    total_episodes: Optional[int] = None
    genres: list[dict] = []


class Chapter(BaseModel):
    number: str
    id: str
    url: Optional[str] = None
    is_downloaded: bool = False


class EpisodeLink(BaseModel):
    server: str
    url: str
    format: Optional[str] = None


class EpisodeLinks(BaseModel):
    stream: dict[str, list[EpisodeLink]] = {'SUB': [], 'DUB': []}
    download: dict[str, list[EpisodeLink]] = {'SUB': [], 'DUB': []}


# ---------------------------------------------------------------------------
# Fase 3: Modelos de API request/response
# ---------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    type: str
    source: str
    content_id: str
    title: str
    exclude_watched: bool = False


class DownloadChapterRequest(BaseModel):
    type: str
    source: str
    content_id: str
    title: str
    chapter_id: str


class DownloadChaptersRequest(BaseModel):
    type: str
    source: str
    content_id: str
    title: str
    chapter_ids: list[str] = []


class StatusUpdateRequest(BaseModel):
    content_ref: str
    status: str

    @field_validator('status')
    @classmethod
    def _valid_status(cls, v: str) -> str:
        allowed = {'watching', 'completed', 'pending', 'none'}
        if v not in allowed:
            raise ValueError(f"Estado inválido: {v}. Permitidos: {', '.join(sorted(allowed))}")
        return v


class WatchedToggleRequest(BaseModel):
    content_ref: str
    chapter: int


class ProgressRequest(BaseModel):
    chapter: str = '1'
    progress: str = '0'
    model_config = {'coerce_numbers_to_str': True}


class DeleteWatchedRequest(BaseModel):
    content_ref: str
    type: str


class DeleteChapterRequest(BaseModel):
    content_ref: str
    type: str
    chapter: int


class AcknowledgeUpdatesRequest(BaseModel):
    content_ref: Optional[str] = None
    content_refs: Optional[list[str]] = None


class SearchQuery(BaseModel):
    type: str
    source: Optional[str] = None
    q: str = ''
    refresh: bool = False


# ---------------------------------------------------------------------------
# Fase 4: Modelos de job de descarga
# ---------------------------------------------------------------------------

class DownloadJob(BaseModel):
    id: int
    content_ref: str
    type: str
    title: str
    chapter_id: Optional[str] = None
    excluded_chapters: list[int] = []
