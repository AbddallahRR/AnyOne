# core/disk_cache.py
import asyncio
import collections
import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "cache"

_DEFAULT_TTL = 60 * 60 * 24
_L1_MAX_ENTRIES = 256


class DiskCache:
    """
    Caché persistente en disco con expiración por tiempo (TTL) y caché L1 en memoria.

    Capas:
      - L1: dict en memoria (max 256 entradas) con TTL, evictión LRU.
      - L2: JSON en disco con escritura atómica.

    Mejoras respecto a la versión original:
      - L1 elimina I/O a disco en las claves más calientes.
      - set() acepta un parámetro ttl opcional que sobreescribe el TTL de
        instancia en esa llamada concreta.
      - Escritura atómica: se escribe en un fichero temporal y luego se
        renombra (rename es atómico en POSIX). Evita JSON corrupto si el
        proceso muere a mitad de escritura.
      - namespace: prefijo que se añade a la clave antes de hashear para
        aislar instancias y evitar colisiones entre módulos.
      - evict_expired(): elimina entradas caducadas de disco (útil al arrancar
        o en un scheduler periódico).
      - aget() / aset(): versiones asíncronas que no bloquean el event loop.
    """

    def __init__(self, ttl: int = _DEFAULT_TTL, namespace: str = 'default'):
        self.ttl = ttl
        self.namespace = namespace
        self._l1: collections.OrderedDict[str, tuple[float, object]] = (
            collections.OrderedDict()
        )
        CACHE_DIR.mkdir(exist_ok=True)

    def _get_path(self, key: str) -> Path:
        if not isinstance(key, str):
            key = json.dumps(key, sort_keys=True)
        namespaced = f"{self.namespace}:{key}"
        hashed = hashlib.md5(namespaced.encode()).hexdigest()
        return CACHE_DIR / f"{hashed}.json"

    def get(self, key: str):
        now = time.time()
        # L1 hit
        entry = self._l1.get(key)
        if entry is not None:
            expires, value = entry
            if expires > now:
                self._l1.move_to_end(key)
                return value
            del self._l1[key]
        # L2 hit (disk)
        path = self._get_path(key)
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data['expires'] > now:
                value = data['value']
                self._l1_put(key, data['expires'], value)
                return value
            path.unlink(missing_ok=True)
            return None
        except (json.JSONDecodeError, KeyError, OSError):
            path.unlink(missing_ok=True)
            return None

    def _l1_put(self, key: str, expires: float, value: object) -> None:
        self._l1[key] = (expires, value)
        self._l1.move_to_end(key)
        while len(self._l1) > _L1_MAX_ENTRIES:
            self._l1.popitem(last=False)

    async def aget(self, key: str):
        return await asyncio.to_thread(self.get, key)

    def set(self, key: str, value, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self.ttl
        expires = time.time() + effective_ttl
        path = self._get_path(key)
        data = {
            'expires': expires,
            'value':   value,
        }
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix='.json.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, path)
            self._l1_put(key, expires, value)
        except OSError:
            logger.warning("Error escribiendo caché a %s", path)
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except Exception as exc:
                    logger.debug('disk_cache: error limpiando archivo temporal %s: %s', tmp_path, exc)

    async def aset(self, key: str, value, ttl: int | None = None) -> None:
        return await asyncio.to_thread(self.set, key, value, ttl)

    def evict_expired(self) -> int:
        now = time.time()
        removed = 0
        for f in CACHE_DIR.glob("*.json"):
            try:
                mtime = f.stat().st_mtime
                if mtime <= now - self._ttl:
                    f.unlink(missing_ok=True)
                    removed += 1
            except Exception as exc:
                logger.debug('disk_cache: error leyendo caché %s: %s', f, exc)
                f.unlink(missing_ok=True)
                removed += 1
        self._l1.clear()
        return removed

    def delete(self, key: str) -> None:
        self._l1.pop(key, None)
        self._get_path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        self._l1.clear()
        for f in CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)


search_cache = DiskCache(ttl=1800, namespace='search')
details_cache = DiskCache(ttl=3600, namespace='details')
chapters_cache = DiskCache(ttl=1800, namespace='chapters')
