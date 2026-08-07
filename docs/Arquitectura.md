---
tags: [anyone, arquitectura]
tema: any
estado: activo
descripcion: Arquitectura, procesos y concurrencia de AnyOne
---

# Arquitectura

AnyOne es una aplicación **monolítica** FastAPI que combina:

1. **Servidor web** — rutas HTML ([[Estructura del Proyecto]]) y API REST (`/api`).
2. **Motor de scraping** — fuentes Python que obtienen contenido de sitios externos.
3. **Sistema de descarga** — cola de trabajos con workers en segundo plano.
4. **Biblioteca local** — escaneo del disco y persistencia en [[Modelo de Datos]].

---

## Flujo de arranque (`app.py`)

1. `init_db()` — crea/actualiza el esquema SQLite (migraciones).
2. `sync_source_settings()` — reconcilia las fuentes descubiertas con la tabla `source_settings`.
3. `cleanup_download_queue()` — marca como fallidos los trabajos interrumpidos y elimina archivos parciales.
4. `start_workers()` — lanza `download_num_workers` (por defecto 3) hilos descargadores.
5. `_start_update_scheduler()` — hilo que comprueba actualizaciones diarias a las **10:00** y limpia la caché de disco cada 24 h.
6. `_warm_all_sources()` — precarga catálogos de fuentes con `warm_cache()` (task asíncrona).

Al apagar: `stop_workers()` detiene los descargadores.

---

## Concurrencia y pools

| Componente | Ubicación | Tamaño |
|---|---|---|
| Workers de descarga | `core/download_worker.py` | `download_num_workers` = 3 |
| Post-proceso ffmpeg (faststart) | `core/download_worker.py` | 2 hilos (`ThreadPoolExecutor`) |
| Ejecutor de métodos sync de fuentes | `sources/__init__.py` | 12 hilos (`BaseSource._executor`) |
| Escaneo de series locales | `core/utils.py` | 8 hilos |
| Comprobación de actualizaciones | `routers/api/updates.py` | 4 hilos |
| Sesiones HTTP por hilo | `core/http_pool.py` | 20 conexiones / 40 máx por sesión |

> Las fuentes implementan métodos `*_sync` y la API async los envuelve con `asyncio.run_in_executor`, de modo que el event loop nunca se bloquea.

---

## Caché en disco

La clase [[DiskCache]] (`core/disk_cache.py`) implementa dos capas:

- **L1:** dict LRU en memoria (256 entradas máx).
- **L2:** JSON en `cache/` con escritura atómica (tempfile + `os.replace`) y TTL.

Instancias singulares:

| Singleton | Namespace | TTL |
|---|---|---|
| `search_cache` | `search` | 1800 s |
| `details_cache` | `details` | 3600 s |
| `chapters_cache` | `chapters` | 1800 s |

`evict_expired()` elimina entradas caducadas y el scheduler la invoca cada 24 h.

---

## Middlewares

- **CORS** — orígenes desde `CORS_ORIGINS` (por defecto `*`).
- **GZip** — comprime respuestas ≥ 500 bytes.
- **CachedStaticFiles** — `Cache-Control` por tipo: `immutable` 1 año para `/dist/`, 30 días para fuentes, 1 día para el resto.

---

## Seguridad relevante

- `_safe_path()` en `routers/api/common.py` protege contra *path traversal* (`.resolve()` + `is_relative_to`).
- `SECRET_KEY` debe cambiarse en producción (advertencia en logs si se usa la clave por defecto).
- El endpoint `entrypoint.py` (Docker) cambia a UID/GID 1000 tras arrancar.

---

## Notas relacionadas
- [[Estructura del Proyecto]]
- [[Modelo de Datos]]
- [[Configuración]]
- [[Fuentes]]
