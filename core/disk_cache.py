# core/disk_cache.py
import asyncio
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


class DiskCache:
    """
    Caché persistente en disco con expiración por tiempo (TTL).

    Mejoras respecto a la versión original:
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
        CACHE_DIR.mkdir(exist_ok=True)

    def _get_path(self, key: str) -> Path:
        if not isinstance(key, str):
            key = json.dumps(key, sort_keys=True)
        namespaced = f"{self.namespace}:{key}"
        hashed = hashlib.md5(namespaced.encode()).hexdigest()
        return CACHE_DIR / f"{hashed}.json"

    def get(self, key: str):
        path = self._get_path(key)
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data['expires'] > time.time():
                return data['value']
            path.unlink(missing_ok=True)
            return None
        except (json.JSONDecodeError, KeyError, OSError):
            path.unlink(missing_ok=True)
            return None

    async def aget(self, key: str):
        return await asyncio.to_thread(self.get, key)

    def set(self, key: str, value, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self.ttl
        path = self._get_path(key)
        data = {
            'expires': time.time() + effective_ttl,
            'value':   value,
        }
        try:
            fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix='.json.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, path)
        except OSError:
            logger.warning("Error escribiendo caché a %s", path)
            try:
                os.unlink(tmp_path)
            except Exception:
                logger.warning('disk_cache: error limpiando archivo temporal %s', tmp_path)

    async def aset(self, key: str, value, ttl: int | None = None) -> None:
        return await asyncio.to_thread(self.set, key, value, ttl)

    def evict_expired(self) -> int:
        now = time.time()
        removed = 0
        for f in CACHE_DIR.glob("*.json"):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                if data.get('expires', 0) <= now:
                    f.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                f.unlink(missing_ok=True)
                removed += 1
        return removed

    def delete(self, key: str) -> None:
        self._get_path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        for f in CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)


search_cache = DiskCache(ttl=_DEFAULT_TTL, namespace='search')
