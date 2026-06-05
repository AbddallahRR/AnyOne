from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    base_download_dir: Path = Path.home() / 'DescargasComics'
    db_dir: Path = Path.home() / '.config' / 'comic_web'
    secret_key: str = Field(default='insecure-dev-key-change-in-production')
    debug: bool = Field(default=False)
    host: str = '0.0.0.0'
    port: int = 5000
    download_num_workers: int = 3

    @property
    def anime_download_dir(self) -> Path:
        return self.base_download_dir / 'Anime'

    @property
    def manga_download_dir(self) -> Path:
        return self.base_download_dir / 'Manga'

    @property
    def db_path(self) -> Path:
        return self.db_dir / 'history.db'

    model_config = {'env_prefix': ''}


settings = Settings()
