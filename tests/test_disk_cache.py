import core.disk_cache as disk_cache
from core.disk_cache import DiskCache


class TestEvictExpired:
    def test_removes_only_expired(self, tmp_path, monkeypatch):
        monkeypatch.setattr(disk_cache, 'CACHE_DIR', tmp_path)
        cache = DiskCache(ttl=3600, namespace='evict')
        cache.set('fresh', 'a', ttl=3600)
        cache.set('stale', 'b', ttl=-1)
        removed = cache.evict_expired()
        assert removed == 1
        assert cache.get('fresh') == 'a'
        assert cache.get('stale') is None
        cache.clear()
