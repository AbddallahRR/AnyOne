import logging
import threading

import cloudscraper
import requests

logger = logging.getLogger(__name__)


class HttpPool:
    _local = threading.local()

    @classmethod
    def get_session(cls) -> requests.Session:
        if not hasattr(cls._local, 'session') or cls._local.session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20,
                pool_maxsize=40,
                max_retries=2,
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)
            cls._local.session = session
        return cls._local.session

    @classmethod
    def get_scraper(cls) -> cloudscraper.CloudScraper:
        if not hasattr(cls._local, 'scraper') or cls._local.scraper is None:
            scraper = cloudscraper.create_scraper()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=20,
                pool_maxsize=40,
                max_retries=2,
            )
            scraper.mount('https://', adapter)
            scraper.mount('http://', adapter)
            cls._local.scraper = scraper
        return cls._local.scraper
