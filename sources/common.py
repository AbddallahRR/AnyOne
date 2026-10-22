import logging
import os
import time

from core.http_pool import HTTP_TIMEOUT, HttpPool
from core.throttle import rate_limiter

logger = logging.getLogger(__name__)


class HttpClientMixin:
    UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

    def __init__(self):
        self.scraper = HttpPool.get_session()

    @property
    def _headers(self) -> dict:
        return {'User-Agent': self.UA}

    def _get(self, url: str, referer: str | None = None, **kwargs):
        rate_limiter.wait(url)
        kwargs.setdefault('timeout', HTTP_TIMEOUT)
        # Para cloudscraper, dejar que gestione headers para resolver challenges de Cloudflare
        import cloudscraper
        if isinstance(self.scraper, cloudscraper.CloudScraper):
            headers = kwargs.pop('headers', {})
            if referer and 'Referer' not in headers:
                headers['Referer'] = referer
            cookies = getattr(self, '_cookies', None)
            if cookies:
                kwargs.setdefault('cookies', cookies)
            if headers:
                kwargs['headers'] = headers
            resp = self.scraper.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        headers = self._headers.copy()
        if referer:
            headers['Referer'] = referer
        extra = kwargs.pop('headers', {})
        headers.update(extra)
        cookies = getattr(self, '_cookies', None)
        if cookies:
            kwargs.setdefault('cookies', cookies)
        resp = self.scraper.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, data=None, referer: str | None = None, **kwargs):
        rate_limiter.wait(url)
        headers = {
            **self._headers,
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        if referer:
            headers['Referer'] = referer
        extra = kwargs.pop('headers', {})
        headers.update(extra)
        cookies = getattr(self, '_cookies', None)
        if cookies:
            kwargs.setdefault('cookies', cookies)
        kwargs.setdefault('timeout', HTTP_TIMEOUT)
        resp = self.scraper.post(url, headers=headers, data=data, **kwargs)
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> dict:
        kwargs.setdefault('headers', {})
        kwargs['headers']['Accept'] = 'application/json'
        return self._get(url, **kwargs).json()

    def _get_with_retry(self, url: str, retries: int = 3,
                        backoff: float = 1.0, **kwargs):
        source_name = getattr(self, 'label', 'Source')
        last_exc = None
        for attempt in range(retries):
            try:
                return self._get(url, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    wait = backoff * (2 ** attempt)
                    log = logger.warning
                    log(
                        f"{source_name}: reintento {attempt + 1}/{retries - 1} "
                        f"para {url[:80]}... (espera {wait:.1f}s): {exc}"
                    )
                    time.sleep(wait)
        raise last_exc


class MangaDownloadHelper:
    @staticmethod
    def count_images(cap_dir: str) -> int:
        from core.utils import count_images_in_dir
        return count_images_in_dir(cap_dir)

    @staticmethod
    def make_chapter_dir(dest_folder: str, chapter_number: str) -> str:
        from core.models import chapter_to_filename
        cap_num = chapter_number or '0'
        dir_name = (
            f"cap_{chapter_to_filename(cap_num)}"
            if cap_num.replace('.', '', 1).isdigit()
            else f"cap_{cap_num}"
        )
        cap_dir = os.path.join(dest_folder, dir_name)
        os.makedirs(cap_dir, exist_ok=True)
        return cap_dir

    @staticmethod
    def download_images(
        img_urls: list[str],
        cap_dir: str,
        headers: dict | None = None,
        retry_get=None,
        progress_cb=None,
        max_workers: int = 1,
    ) -> int:
        """Download chapter images into *cap_dir* as 0001.ext, 0002.ext, ...

        Returns the number of failures. *retry_get* must take (url, **kwargs)
        and return a response usable as a context manager. Set *max_workers* > 1
        to download concurrently, passing a retry_get that resolves its own
        per-thread session.
        """
        from core.html_utils import url_ext

        dl_headers = dict(headers or {})
        get_fn = retry_get or (lambda url, **kw: __import__('requests').get(url, **kw))
        total = len(img_urls)
        tasks = list(enumerate(img_urls, start=1))

        def _fetch(task) -> bool:
            i, img_url = task
            ext = url_ext(img_url)
            filepath = os.path.join(cap_dir, f"{i:04d}.{ext}")
            if os.path.exists(filepath):
                return True
            try:
                with get_fn(img_url, headers=dl_headers, stream=True) as resp:
                    resp.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            f.write(chunk)
                return True
            except Exception as exc:
                logger.exception(f"Error descargando imagen {i} ({img_url[:60]}): {exc}")
                return False

        if max_workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                results = list(pool.map(_fetch, tasks))
        else:
            results = [_fetch(t) for t in tasks]

        failures = 0
        for i, ok in enumerate(results, start=1):
            if not ok:
                failures += 1
            if progress_cb:
                progress_cb(i, total, f'Imagen {i}/{total}')
        return failures
