import threading
import time
from urllib.parse import urlparse


class RateLimiter:
    """Per-domain rate limiter with token bucket algorithm.

    Uses threading.Event for precise wake-up instead of busy-wait loops.
    """

    def __init__(self, min_interval: float = 2.0):
        self.min_interval = min_interval
        self._last_calls: dict[str, float] = {}
        self._lock = threading.Lock()
        self._events: dict[str, threading.Event] = {}

    def _get_remaining(self, domain: str) -> float:
        now = time.time()
        elapsed = now - self._last_calls.get(domain, 0.0)
        return max(0.0, self.min_interval - elapsed)

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        if not domain:
            return

        with self._lock:
            remaining = self._get_remaining(domain)
            if remaining <= 0:
                self._last_calls[domain] = time.time()
                return
            event = self._events.setdefault(domain, threading.Event())

        event.wait(timeout=remaining)

        with self._lock:
            self._last_calls[domain] = time.time()
            event.clear()


rate_limiter = RateLimiter(min_interval=1.0)
