import logging

import cloudscraper
import requests

logger = logging.getLogger(__name__)


class HttpPool:
    _shared_session: requests.Session | None = None
    _shared_scraper: cloudscraper.CloudScraper | None = None

    @classmethod
    def get_session(cls) -> requests.Session:
        if cls._shared_session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20,
                pool_maxsize=40,
                max_retries=2,
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            cls._shared_session = session
        return cls._shared_session

    @classmethod
    def get_scraper(cls) -> cloudscraper.CloudScraper:
        if cls._shared_scraper is None:
            cls._shared_scraper = cloudscraper.create_scraper()
            cls.get_session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20,
                pool_maxsize=40,
                max_retries=2,
            )
            cls._shared_scraper.mount('https://', adapter)
            cls._shared_scraper.mount('http://', adapter)
        return cls._shared_scraper
