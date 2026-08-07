---
tags: [anyone, fuentes, indice, moc]
tema: any
estado: activo
descripcion: Mecanismo de fuentes de contenido de AnyOne
---

# Fuentes

Las fuentes son clases Python que implementan el contrato [[Fuentes#BaseSource|BaseSource]] en `sources/`. AnyOne las **descubre automáticamente** al arrancar.

## Contrato `BaseSource` (`sources/__init__.py`)

Cada fuente define:

| Método | Descripción |
|---|---|
| `search(query)` | Busca y devuelve `list[SearchResult]` |
| `get_details(content_id)` | Devuelve `SeriesDetails` |
| `get_chapters(content_id)` | Devuelve `list[Chapter]` |
| `download_chapter(content_id, chapter_id, dest_folder, chapter_number)` | Descarga un capítulo; devuelve la ruta creada |
| `supports_streaming` | Propiedad: `True` si puede emitir vídeo remoto |
| `get_stream_url(content_id, chapter_id)` | URL del servidor de streaming (anime) |
| `get_chapter_images(content_id, chapter_id)` | URLs de imágenes sin descargar (lector de manga) |
| `warm_cache()` | Precarga opcional del catálogo |

**Patrón sync/async:** las subclases implementan `*_sync` y la clase base envuelve la llamada con un `ThreadPoolExecutor` de 12 hilos, de modo que el event loop no se bloquea.

## Descubrimiento y registro (`core/sources.py`)

1. `_discover_sources()` recorre `sources/` e importa cada módulo.
   - Se **omite** cualquier archivo que contenga `--- IGNORE ---` (por eso `manhwaweb.py` y `nartag.py` están deshabilitadas).
   - Se registra en `SOURCES[type][name]` (nombre = clase en minúsculas sin sufijo `Source`) y en `ALL_SOURCES_META`.
2. Al arrancar, `sync_source_settings()` reconcilia las fuentes con la tabla `source_settings` y limpia huérfanas.
3. Las configuraciones dinámicas se cargan con `load_dynamic_sources()`.
4. `get_enabled_sources(type)` devuelve solo las **habilitadas** y **disponibles** (no desactivadas por el circuit breaker).

## Fuentes actuales

| Fuente | Tipo | Estado | Nota |
|---|---|---|---|
| [[Fuente - JKanime]] | anime | Activa | jkanime.net — vídeo, streaming, SUB/DUB |
| [[Fuente - Ikigai]] | manga | Activa | visualikigai — catálogo + imágenes |
| [[Fuente - Dinámica]] | ambos | Activa | scrapers configurables por el usuario |
| ManhwaWeb | manga | Deshabilitada | `--- IGNORE ---` (referencia) |
| Nartag | manga | Deshabilitada | `--- IGNORE ---` (referencia) |

## Infraestructura compartida

- **HTTP:** `core/http_pool.py` — sesiones por hilo con `cloudscraper` (bypass Cloudflare) y `Retry` en `429/5xx`.
- **Throttling:** `core/throttle.py` — 1 s mínimo por dominio.
- **Caché:** `core/disk_cache.py` ([[DiskCache]]).
- **Salud:** `core/scraper_health.py` — 3 fallos consecutivos desactivan la fuente 5 min.
- **Helpers de manga:** `sources/common.py` — `MangaDownloadHelper` (descarga de imágenes, carpetas `cap_*`).
- **Extracción de imágenes:** `core/html_utils.py` — estrategias de `<noscript>`, scripts JS (Qwik, NUXT, NEXT_DATA, `ts_reader`, `madara_*`), srcset, background-image.

---

## Notas relacionadas
- [[AnyOne - Inicio]]
- [[Fuente - JKanime]]
- [[Fuente - Ikigai]]
- [[Fuente - Dinámica]]
- [[API - Configuración de Fuentes]]
