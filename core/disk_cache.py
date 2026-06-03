# core/disk_cache.py
import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Directorio de caché (en la raíz del proyecto, carpeta 'cache')
CACHE_DIR = Path(__file__).parent.parent / "cache"

_DEFAULT_TTL = 60 * 60 * 24   # 24 horas


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
    """

    def __init__(self, ttl: int = _DEFAULT_TTL, namespace: str = 'default'):
        self.ttl = ttl
        self.namespace = namespace
        CACHE_DIR.mkdir(exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Genera la ruta del archivo de caché a partir de la clave."""
        if not isinstance(key, str):
            key = json.dumps(key, sort_keys=True)
        # Incluir namespace evita colisiones entre instancias distintas
        namespaced = f"{self.namespace}:{key}"
        hashed = hashlib.md5(namespaced.encode()).hexdigest()
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
            path.unlink(missing_ok=True)
            return None
        except (json.JSONDecodeError, KeyError, OSError):
            # Archivo corrupto o estructura inesperada — lo descartamos
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, value, ttl: int | None = None) -> None:
        """
        Guarda un valor en la caché.

        Args:
            key:   Clave de caché.
            value: Valor serializable en JSON.
            ttl:   TTL en segundos para esta entrada. Si es None, usa self.ttl.
        """
        effective_ttl = ttl if ttl is not None else self.ttl
        path = self._get_path(key)
        data = {
            'expires': time.time() + effective_ttl,
            'value':   value,
        }

        # Escritura atómica: temporal en el mismo directorio → rename
        try:
            fd, tmp_path = tempfile.mkstemp(dir=CACHE_DIR, suffix='.json.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, path)   # atómico en POSIX y Windows (Python 3.3+)
        except OSError:
            logger.warning("Error escribiendo caché a %s", path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def evict_expired(self) -> int:
        """
        Elimina del disco todas las entradas expiradas.
        Devuelve el número de archivos eliminados.
        Llamar al arrancar la app o en un scheduler periódico para mantener
        la carpeta cache/ limpia.
        """
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
                # Archivo corrupto — también lo eliminamos
                f.unlink(missing_ok=True)
                removed += 1
        return removed

    def delete(self, key: str) -> None:
        """Elimina una entrada de la caché."""
        self._get_path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        """Limpia toda la caché."""
        for f in CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)


# Instancia global
search_cache = DiskCache(ttl=_DEFAULT_TTL, namespace='search')