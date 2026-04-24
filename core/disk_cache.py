# core/disk_cache.py
import os
import json
import hashlib
import time
from pathlib import Path

# Directorio de caché (en la raíz del proyecto, carpeta 'cache')
CACHE_DIR = Path(__file__).parent.parent / "cache"

class DiskCache:
    """Caché persistente en disco con expiración por tiempo (TTL)."""
    def __init__(self, ttl=43200):  # 12 horas por defecto
        self.ttl = ttl
        CACHE_DIR.mkdir(exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Genera la ruta del archivo de caché a partir de la clave."""
        if not isinstance(key, str):
            key = json.dumps(key, sort_keys=True)
        hashed = hashlib.md5(key.encode()).hexdigest()
        return CACHE_DIR / f"{hashed}.json"

    def get(self, key: str):
        """Obtiene el valor de la caché si no ha expirado, o None."""
        path = self._get_path(key)
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data['expires'] > time.time():
                return data['value']
            else:
                # Expirado, lo borramos
                path.unlink()
                return None
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value):
        """Guarda un valor en la caché con el TTL configurado."""
        path = self._get_path(key)
        data = {
            'expires': time.time() + self.ttl,
            'value': value
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def delete(self, key: str):
        """Elimina una entrada de la caché."""
        path = self._get_path(key)
        if path.exists():
            path.unlink()

    def clear(self):
        """Limpia toda la caché."""
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()

# Instancia global para usar en la aplicación
search_cache = DiskCache(ttl=43200)  # 24 horas