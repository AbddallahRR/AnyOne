import time
import threading
from urllib.parse import urlparse

class RateLimiter:
    """Per-domain rate limiter to avoid getting banned by upstream sources."""

    def __init__(self, min_interval: float = 2.0):
        self.min_interval = min_interval
        self._last_calls: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        if not domain:
            return
        while True:
            with self._lock:
                now = time.time()
                elapsed = now - self._last_calls.get(domain, 0.0)
                if elapsed >= self.min_interval:
                    self._last_calls[domain] = now
                    return
                sleep_for = self.min_interval - elapsed
            time.sleep(sleep_for)

rate_limiter = RateLimiter(min_interval=2.0)
