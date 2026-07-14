# AnyOne — Arquitectura

Aplicación web FastAPI para buscar, descargar y leer/ver anime y manga desde múltiples fuentes (scrapers).

La aplicación usa un modelo **híbrido sync/async**: la API FastAPI es completamente async,
los scrapers exponen métodos sync (para los workers de descarga en hilos) y async (para la API).
El puente entre ambos mundos es `asyncio.to_thread()`.

---

## Estructura general

```
AnyOne/
├── app.py                    → Factory de la app FastAPI
├── entrypoint.py             → Punto de entrada Docker (solo contenedor)
├── requirements.txt          → Dependencias Python
├── pyproject.toml            → Configuración del proyecto (ruff, mypy)
├── Dockerfile                → Imagen Docker (python:3.12-slim)
├── docker-compose.yml        → Orquestación local
│
├── routers/                  → FastAPI routers
│   ├── pages.py              →   Rutas HTML (/, /serie, /reader)
│   └── api/                  →   API REST (/api/*)
│       ├── __init__.py       →   Crea el APIRouter (/api) e importa todos los sub-routers
│       ├── common.py         →   Helpers compartidos (índice en memoria, cola, fs)
│       ├── settings.py       →   Configuración de fuentes (/api/settings*)
│       ├── search.py         →   Búsqueda en fuentes (/api/search*)
│       ├── content.py        →   Detalle, capítulos y contenido (/api/content, /api/chapters*)
│       ├── media.py          →   Reproducción, portadas y archivos (/api/play*, /api/local-cover, /api/manga/images)
│       ├── library.py        →   Biblioteca, etiquetas, vistos (/api/library*)
│       ├── progress.py       →   Progreso de usuario (/api/progress*)
│       ├── watched.py        →   Capítulos vistos y eliminación (/api/watched*, /api/delete-watched, /api/delete-chapter, /api/delete-series)
│       ├── downloads.py      →   Cola de descarga (/api/download, /api/queue)
│       ├── updates.py        →   Comprobación de capítulos nuevos
│       ├── scraper_configs.py →   CRUD de scrapers dinámicos (/api/scraper-configs)
│       ├── scraper_tester.py →   Testeo y auto-detección de scrapers (/api/scraper-configs/test, /api/scraper-configs/auto-detect, /api/scraper-configs/detect-selectors, /api/scraper-health*)
│       └── dependencies.py   →   Dependencias FastAPI compartidas (get_source con validación)
│
├── core/                     → Lógica compartida
│   ├── database.py           →   Fachada que re-exporta desde core/db/*
│   ├── db/                   →   Paquete de acceso a SQLite
│   │   ├── __init__.py       →   Re-exporta todo desde los submódulos
│   │   ├── connection.py     →   Conexión WAL, migraciones versionadas (v10)
│   │   ├── content.py        →   CRUD de contenidos
│   │   ├── downloads.py      →   Cola de descarga
│   │   ├── library.py        →   Estado de series, actualizaciones
│   │   ├── progress.py       →   Progreso de usuario
│   │   ├── settings.py       →   Configuración de fuentes (activo/inactivo)
│   │   └── watched.py        →   Capítulos vistos
│   ├── disk_cache.py         →   Caché JSON en disco con TTL
│   ├── download_worker.py    →   Workers en hilos para descarga
│   ├── http_pool.py          →   Pool HTTP compartido (Session + Scraper)
│   ├── models.py             →   Modelos Pydantic (validación, serialización)
│   ├── settings.py           →   Config tipada con pydantic-settings
│   ├── sources.py            →   Registro de fuentes disponibles
│   ├── throttle.py           →   Rate limiter por dominio
│   ├── scraper_config.py     →   Gestión de scrapers dinámicos (carga, validación, persistencia)
│   ├── scraper_health.py     →   Salud de scrapers (fallo consecutivo, cooldown, re-habilitación)
│   ├── selector_detector.py  →   Inferencia automática de selectores CSS desde HTML
│   ├── html_utils.py         →   Utilidades de parsing HTML (extractores de imágenes, normalización de URLs, srcset)
│   ├── chapter_utils.py      →   Utilidades de capítulos decimales (normalización, nombre de archivo, parsing)
│   └── utils.py              →   Normalización de títulos, escaneo local
│
├── sources/                  → Scrapers (uno por sitio upstream)
│   ├── __init__.py           →   Clase base BaseSource
│   ├── common.py             →   Mixin HTTP (HttpClientMixin) y helper de descarga manga (MangaDownloadHelper)
│   ├── jkanime.py            →   jkanime.net (anime)
│   ├── nartag.py             →   nartag.com (manga)
│   ├── manhwaweb.py          →   manhwaweb.com (manga)
│   ├── ikigai.py             →   visorikigai (manga)
│   └── dynamic.py            →   Motor de scrapers dinámicos definidos por el usuario
│
├── templates/                → Jinja2 (server-side rendered)
│   ├── base.html             →   Layout: fonts, icons, CSS, JS globales
│   ├── index.html            →   Home: búsqueda + biblioteca
│   ├── serie.html            →   Detalle de serie (capítulos, portada)
│   ├── reader.html           →   Lector de video / manga
│   └── settings.html         →   Wizard de 6 pasos para crear scrapers dinámicos
│
├── scripts/
│   └── build.py              →   Build: bundle + minify + content hash
│
├── tests/                    → Tests unitarios
│   ├── test_html_utils.py    →   Tests de utilidades HTML
│   └── test_selector_detector.py → Tests de detector de selectores
│
└── static/                   → Frontend
    ├── css/
    │   ├── base.css          →   Design tokens, componentes (cards, modal, spinner…)
    │   ├── layout.css        →   Nav, page-content, responsive breakpoints
    │   ├── index.css         →   Filtros de biblioteca
    │   ├── serie.css         →   Cover parallax, hero, synopsis
    │   ├── reader.css        →   Lector full-screen, controles
    │   ├── settings.css      →   Wizard de scrapers dinámicos (detect-section, pasos)
    │   ├── inter.css         →   Face-font de Inter (local, woff2)
    │   └── fa-subset.css     →   Subset de FA solo con los 28 iconos usados
    ├── fonts/
    │   └── Inter-{400,500,600,700,800}.woff2     → Pesos de Inter (woff2, eliminados TTF originales)
    ├── webfonts/
    │   ├── fa-solid-900.woff2           → Font Awesome completo (solo dev)
    │   ├── fa-solid-900-subset.woff2    → Subset con solo los 28 iconos usados
    │   ├── fa-regular-400.woff2         → No usado, mantenido por compatibilidad
    │   └── fa-brands-400.woff2          → No usado, mantenido por compatibilidad
    ├── js/
    │   ├── api.js            →   Wrapper HTTP global (GET con dedup, POST, PUT, DELETE)
    │   ├── app.js            →   Lógica de index.html
    │   ├── serie.js          →   Lógica de serie.html
    │   ├── reader.js         →   Lógica de reader.html
    │   ├── settings.js       →   Lógica de settings.html (wizard de scrapers dinámicos)
    │   ├── queue-indicator.js →  Indicador flotante de descargas
    │   ├── scraper-health.js →  Indicador de salud de scrapers (fallo/cooldown)
    │   ├── toast.js          →  Notificaciones toast (éxito/error/info)
    │   └── confirm.js        →  Diálogo de confirmación global (Promise-based)
    └── dist/                  →   Output del build (generado)
        ├── build.json        →   Manifiesto: nombre real de cada bundle con hash
        ├── index.{hash}.css  →   CSS empaquetado para index.html
        ├── index.{hash}.js   →   JS empaquetado para index.html
        ├── serie.{hash}.css  →   CSS empaquetado para serie.html
        ├── serie.{hash}.js   →   JS empaquetado para serie.html
        ├── reader.{hash}.css →   CSS empaquetado para reader.html
        ├── reader.{hash}.js  →   JS empaquetado para reader.html
        ├── settings.{hash}.css → CSS empaquetado para settings.html
        └── settings.{hash}.js  → JS empaquetado para settings.html
```

---

## Módulos — descripción y funcionamiento

### `core/settings.py` — Configuración tipada

Usa `pydantic-settings.BaseSettings` para leer variables de entorno con
validación automática y type hints:

| Variable | Tipo | Default | Descripción |
|----------|------|---------|-------------|
| `BASE_DOWNLOAD_DIR` | `Path` | `~/DescargasComics` | Carpeta raíz de descargas |
| `DB_DIR` | `Path` | `~/.config/comic_web` | Carpeta de BD SQLite |
| `SECRET_KEY` | `str` | `insecure-dev-key-...` | Firma de cookies (requerido en prod) |
| `DEBUG` | `bool` | `False` | Modo debug |
| `HOST` | `str` | `0.0.0.0` | Bind del servidor |
| `PORT` | `int` | `5000` | Puerto del servidor |
| `DOWNLOAD_NUM_WORKERS` | `int` | `3` | Workers de descarga |

Propiedades derivadas: `anime_download_dir`, `manga_download_dir`, `db_path`.

Crea automáticamente los directorios en la instanciación.

---

### `core/models.py` — Modelos Pydantic

Define todos los contratos de datos del proyecto usando Pydantic v2:

**Contratos de fuentes:**
- `SearchResult` — `{id, title, cover, source, type, last_chapter, progress}`
- `SeriesDetails` — `{title, cover, synopsis, type, total_episodes, genres}`
- `Chapter` — `{number, id, url, is_downloaded}`
- `EpisodeLink` / `EpisodeLinks` — links de stream/descarga por variante

**Modelos de API request:**
- `DownloadRequest`, `DownloadChapterRequest`, `DownloadChaptersRequest`
- `StatusUpdateRequest` — valida que status sea `watching|completed|pending|none`
- `WatchedToggleRequest`, `ProgressRequest`, `DeleteWatchedRequest`, `DeleteChapterRequest`, `DeleteSeriesRequest`
- `AcknowledgeUpdatesRequest` — acepta `content_ref` (único) o `content_refs` (lista)
- `SearchQuery` — inyectado vía `Depends()` en endpoints de búsqueda
- `CreateScraperConfigRequest` — crea scraper dinámico (name, type, label, base_url, config)
- `UpdateScraperConfigRequest` — actualiza scraper (label, base_url, enabled, config, todos opcionales)
- `SourceSettingsRequest` — body vacío para endpoints de settings
- `ReEnableRequest` — re-habilita un scraper deshabilitado (name)

Nota: los campos `chapter` en `WatchedToggleRequest` y `DeleteChapterRequest`, y `excluded_chapters` en `DownloadJob` son de tipo `str` para soportar capítulos decimales (ej. `"5.5"`).

**Modelos de scrapers dinámicos:**
- `ScraperConfigSchema` — schema de configuración de scrapers dinámicos con 39 campos para búsqueda (`search_url_template`, `search_result_selector`, `search_method`, `search_has_pagination`, etc.), detalles, capítulos, contenido (`content_type`, `content_image_selector`, `content_image_attr`, `content_video_selector`, `content_extra_attrs`, `content_detected_pattern`) y catálogo (`has_catalog`, `catalog_url_template`, `catalog_item_selector`, `catalog_max_pages`, `catalog_cache_ttl`, etc.). Soporta headers y cookies extra, y `use_cloudscraper`.

**Modelos internos:**
- `DownloadJob` — job tipado para la cola de descarga

**Helpers de capítulos decimales (re-exportados desde `core.chapter_utils`):**
- `chapter_to_filename(chapter: str, padding: int = 4)` — convierte `"5.5"` → `"0005_5"` para nombres de archivo/carpeta
- `parse_chapter_from_filename(filename: str)` — extrae `"5.5"` de `"serie_005_5.mp4"` o `"serie_005.mp4"` (compatible con enteros)

Todos los endpoints usan `_parse_json_body(modelo)` que lanza `ValidationError`
ante datos inválidos. El error handler global en `app.py` lo captura y retorna
400 con detalles del error.

---

### `app.py` — Application entry point

Punto de entrada. Usa `lifespan` de FastAPI:

1. Crea la app FastAPI, activa CORS
2. Ejecuta migraciones de BD (`init_db`)
3. Sincroniza fuentes registradas con la tabla `source_settings` (`sync_source_settings()`)
4. Limpia la cola de descargas interrumpidas (`cleanup_download_queue`)
5. Inicia `DOWNLOAD_NUM_WORKERS` workers de descarga en hilos daemon
6. Arranca el scheduler de actualizaciones (daemon thread, cada 24 h) que ejecuta `_check_all_updates_core()` y `evict_expired()` en caché
7. Emite warning si `SECRET_KEY` tiene el valor inseguro por defecto
8. Monta `CachedStaticFiles` (con headers de caché por ruta) y registra los routers (`pages`, `api`)
9. Lanza precarga en background de todas las fuentes (`asyncio.create_task(_warm_all_sources())`)
10. Al shutdown: detiene los workers gracefulmente (`stop_workers()`)

La precarga de catálogos (`_warm_all_sources`) ejecuta todos los `warm_cache()` en paralelo
con `asyncio.gather()` y timeout de 30 s por fuente.

**Health check:** `GET /health` → `{'status': 'ok'}` para monitoreo del contenedor.

---

### `routers/pages.py` — Rutas HTML

Tres rutas que renderizan templates Jinja2:

| Ruta | Template | Función |
|------|----------|---------|
| `/` | `index.html` | Página principal (búsqueda + biblioteca local) |
| `/serie/<type>/<source>/<id>` | `serie.html` | Detalle de serie y lista de capítulos |
| `/reader/<type>/<source>/<content_id>/<chapter>` | `reader.html` | Lector/reproductor a pantalla completa |
| `/settings` | `settings.html` | Wizard de scrapers dinámicos (6 pasos) |

La ruta `/serie` determina si la fuente soporta streaming (`can_stream`) consultando
`src.supports_streaming` en el backend. Para fuentes manga siempre retorna `true`;
para anime depende de que la fuente implemente `get_stream_url()`. El flag se pasa
al template como `window.serieData.canStream` para que el frontend muestre u oculte
el botón "Reproducir en streaming".

---

### `routers/api/` — API REST (paquete)

Antes un solo archivo de ~1180 líneas (Flask), ahora modularizado en 11 submódulos con FastAPI. Corazón del backend. El `__init__.py` crea el `api_router` con prefijo `/api`, importa todos los sub-módulos (registrando sus rutas) y re-exporta `_invalidate_series_index` y `_check_all_updates_core` para uso externo.

---

#### `api/common.py` — Helpers compartidos

Funciones y estado global reutilizados por todos los submódulos:

- `_safe_path(base, untrusted)` — previene path traversal
- `_build_series_index` / `_get_series_index` / `_invalidate_series_index` — índice en memoria de series locales (content_id → Path). `_build_series_index` usa `ThreadPoolExecutor(8)` para leer los `series_info.json` en paralelo.
- `_find_local_serie_dir` — busca carpeta por content_id (índice O(1) + fallback por normalización)
- `_local_chapters_anime` / `_local_chapters_manga` — lista capítulos locales
- `_delete_chapter_files` — elimina archivos de un capítulo en disco
- `_resolve_series_title` — resuelve título desde BD o disco
- `_base_folder` / `_require_local` / `_content_title_by_ref` — utilidades menores

---

#### `api/search.py` — Búsqueda

Los endpoints son `async def` y hacen `await` a los métodos async de las fuentes. Las claves de caché incorporan fingerprints de fuentes habilitadas (nombres ordenados) para invalidarse cuando cambia la configuración.

- `GET /api/search?type=...&source=...&q=...` — busca en una fuente (con caché en `search_cache` y enriquecimiento con progreso). La caché se consulta con `search_cache.aget()` (async).
- `GET /api/search-all?type=...&q=...` — busca en todas las fuentes del tipo concurrentemente con `asyncio.gather` + dedup por `source:id`.
- `GET /api/search-all-stream?type=...&q=...` — SSE con resultados progresivos (timeout 90s por fuente, cachea para visitas posteriores). Usa `asyncio.wait(FIRST_COMPLETED)` para emitir resultados tan pronto como cualquiera completa. Emite eventos `source_error` para fuentes desactivadas temporalmente.

---

#### `api/content.py` — Detalle y capítulos

- `GET /api/content/<type>/<source>/<id>` — portada, sinopsis. Parámetro `refresh` fuerza bypass de caché.
- `GET /api/chapters/<type>/<source>/<id>` — lista remota de capítulos. Parámetro `refresh` fuerza bypass de caché.
- `GET /api/chapters/with-local/<type>/<source>/<id>` — remotos marcando descargados
- `GET /api/content/local/<type>/<id>` — detalle de contenido local
- `GET /api/chapters/local/<type>/<id>` — capítulos locales en disco
- `POST /api/cache/clear/<type>/<source>/<id>` — invalida caché de detalles, capítulos y búsqueda para una serie

---

#### `api/media.py` — Reproducción y archivos

- `GET /api/local-cover/<type>/<path:filename>` — sirve portada local (soporta `?thumb=1` para thumbnail WebP, con `Cache-Control` y `ETag` para caché HTTP y soporte 304)
- `GET /api/play/<type>/<source>/<id>/<chapter>` — sirve video local por source/content_id (legacy, solo anime)
- `GET /api/play/local/<type>/<id>/<chapter>` — reproducción local: anime sirve video con range requests (206), manga retorna lista de rutas de imágenes. Soporta `chapter` como string para decimales.
- `GET /api/play/remote/<type>/<source>/<id>/<chapter>` — streaming remoto: anime → redirect 307 a CDN, manga → JSON con URLs de imágenes. Para manga, aplica `filter_manga_images()` para eliminar imágenes pequeñas (logos, anuncios, thumbnails < 300px) que causan saltos en el visor.
- `GET /api/manga/images/<path:subpath>` — imágenes de manga con path safety check, `Cache-Control: max-age=86400` y `ETag` para 304 Not Modified
- `GET /api/video-duration/anime/<id>/<chapter>` — duración del video con `ffprobe` (cacheada por mtime, 24h)

El servidor de video (`_serve_video`) soporta range requests completos: ETag 304, contenido parcial 206 con `Content-Range`, streaming chunked (64KB).

---

#### `api/library.py` — Biblioteca y etiquetas

- `GET /api/library` — lista de series descargadas
- `GET/POST /api/library/status` y `GET /api/library/status/<ref>` — etiquetas (watching/completed/pending/none)
- `GET /api/library/updates` — series con capítulos nuevos pendientes
- `GET /api/library/recent` — 10 series más recientemente accedidas (con progreso)
- `POST /api/library/acknowledge-updates` — limpia flag de novedades (acepta `content_ref` o `content_refs`)

---

#### `api/progress.py` — Progreso de usuario

- `GET /api/progress/local/<type>/<id>` — progreso de contenido local
- `POST /api/progress/local/<type>/<id>` — guarda progreso de contenido local
- `GET /api/progress/<type>/<source>/<content_id>` — progreso de contenido remoto
- `POST /api/progress/<type>/<source>/<content_id>` — guarda progreso de contenido remoto

El progreso funciona para cualquier `content_ref` ("fuente:id"), tanto local como remoto. Se guarda automáticamente desde `reader.js` (cada 15 s para video, al hacer scroll para manga) y se muestra en la página de serie incluso para fuentes no locales. El campo `updated_at` permite ordenamiento por actividad reciente.

---

#### `api/watched.py` — Capítulos vistos y eliminación

- `POST /api/watched` — marca capítulo visto
- `GET /api/watched/<ref>` — lista de capítulos vistos
- `POST /api/watched/toggle` — marca/desmarca (retorna `'watched'` o `'unwatched'`)
- `POST /api/delete-watched` — elimina del disco capítulos vistos (excepto el último). Salta capítulos en descarga activa (devuelve lista `skipped`). Elimina entradas de BD en batch.
- `POST /api/delete-chapter` — elimina un capítulo individual, retrocede progreso si era el último (al capítulo restante más alto). Rechaza con 409 si el capítulo está siendo descargado.
- `POST /api/delete-series` — elimina una serie completa del disco y de 5 tablas de BD (`user_progress`, `watched_chapters`, `series_status`, `content`, `download_queue`). Lee `series_info.json` para obtener la referencia original.

---

#### `api/downloads.py` — Cola de descarga

- `GET /api/queue/status` — jobs activos y pendientes
- `POST /api/download` — encola serie completa (soporta `exclude_watched`). Rechaza con 409 si ya está en cola.
- `POST /api/download/chapter` — encola un capítulo individual. Rechaza con 409 si ya está en cola.
- `POST /api/download/chapters` — encola múltiples capítulos en batch. Silenciosamente ignora duplicados.

**Backpressure:** la cola tiene `maxsize=50`. Si está llena, los endpoints responden `503 Service Unavailable`.

---

#### `api/updates.py` — Comprobación de actualizaciones

- `POST /api/library/check-updates/<ref>` — comprueba capítulos nuevos para una serie
- `POST /api/library/check-all-updates` — comprueba todas las series en paralelo (max 4 workers)
- `_check_series_for_new_chapters(ref)` — lógica central: parsea `source:content_id`, determina tipo (anime/manga) revisando directorios de descarga, obtiene capítulos remotos después del máximo capítulo local, compara con `chapter_float_key` para orden numérico, retorna capítulos nuevos con sus IDs.
- `_check_all_updates_core()` — versión paralela usando `ThreadPoolExecutor(max_workers=4)`, llamada por el scheduler en `app.py`.

---

#### `api/settings.py` — Configuración de fuentes

Endpoints CRUD para activar/desactivar fuentes desde el frontend:

- `GET /api/settings/sources` — devuelve todas las fuentes con su estado (activo/inactivo)
- `PUT /api/settings/sources` — actualiza estados en batch (acepta `{nombre_fuente: bool}` en body)

Usado por el popup de configuración (icono engranaje en `index.html`).

---

#### `api/scraper_configs.py` — CRUD de scrapers dinámicos

Endpoints para gestionar scrapers definidos por el usuario:

- `GET /api/scraper-configs` — lista todas las configuraciones guardadas
- `GET /api/scraper-configs/<name>` — obtiene una configuración por nombre
- `POST /api/scraper-configs` — crea una nueva configuración (valida nombre, tipo, selectores CSS)
- `PUT /api/scraper-configs/<name>` — actualiza una configuración existente (label, base_url, enabled, config)
- `DELETE /api/scraper-configs/<name>` — elimina una configuración (built-in no se pueden eliminar)

---

#### `api/scraper_tester.py` — Testeo y auto-detección de scrapers

Endpoints para probar y detectar selectores de scrapers dinámicos:

- `POST /api/scraper-configs/test` — prueba una configuración contra una URL real (soporta stages `search`, `details`, `chapters`, `content`; para `content` el límite de previsualización de imágenes se eliminó, mostrando todas las encontradas)
- `POST /api/scraper-configs/check-url` — verifica si una URL es alcanzable via HEAD
- `POST /api/scraper-configs/auto-detect` — infiere selectores automáticamente desde una URL usando `selector_detector.py`
- `POST /api/scraper-configs/detect-selectors` — detecta selectores CSS buscando elementos que contengan un texto visible específico (útil para sitios con selectores genéricos). Usa `detect_selector_by_text()` de `selector_detector.py`. Soporta stages `search`, `details`, `chapters`, `content`.
- `POST /api/scraper-configs/auto-configure` — auto-configura un scraper completo: busca selectores de búsqueda, detalles y capítulos en una sola llamada
- `GET /api/scraper-health` — estado de salud de todas las fuentes (errores, desactivaciones temporales)
- `POST /api/scraper-health/re-enable` — re-habilita una fuente desactivada por fallos

---

#### `api/dependencies.py` — Dependencias FastAPI

- `get_source(content_type, source)` — FastAPI dependency que valida que la fuente exista y esté habilitada, retornando la instancia o lanzando HTTPException
- Nota: actualmente definido pero no utilizado por ningún endpoint (cada módulo hace su propia búsqueda de fuente)

---

### `core/database.py` — Fachada SQLite

Módulo fachada que re-exporta todas las funciones de acceso a BD desde `core/db/*`:

```python
from core.db.connection import init_db, get_conn, cleanup_download_queue, execute_with_retry
from core.db.content import save_content_to_db, get_content_ref, delete_content_from_db
from core.db.downloads import update_queue_status, queue_find_active, queue_insert, queue_get_status
from core.db.library import set_series_status, get_series_status, get_all_series_statuses, ...
from core.db.progress import get_progress, save_progress, get_recent_progress
from core.db.settings import get_source_settings, update_source_settings, ...
from core.db.watched import mark_chapter_as_watched, is_chapter_watched, ...
```

La implementación real vive en `core/db/` con un módulo por dominio.

---

### `core/db/` — Paquete de acceso a BD

Conexión por hilo (`threading.local()`) con WAL mode, 32MB cache, foreign keys y 60s busy timeout. Usa `_db_write_lock` para operaciones de escritura concurrentes.

#### `core/db/connection.py` — Conexión y migraciones

**Migraciones versionadas** (versión actual: 10):
- Tablas: `content`, `user_progress`, `download_queue`, `watched_chapters`, `series_status`, `schema_version`, `source_settings`, `scraper_configs`
- Migración #8: cambia `watched_chapters.chapter_number` de INTEGER a TEXT para soportar capítulos decimales (ej. 5.5)
- Migración #9: índices `idx_queue_content_ref_status`, `idx_queue_status_created`, `idx_series_status_check`, `idx_series_status_updates` para eliminar full scans
- Migración #10: columna `updated_at` en `user_progress` para ordenamiento por actividad reciente

**Operaciones:**
- `init_db()` — crea esquema y aplica migraciones (con retry si la BD está bloqueada)
- `cleanup_download_queue()` — al arrancar, limpia descargas interrumpidas
- `get_conn()` — retorna conexión thread-local con WAL mode y parámetros optimizados
- `execute_with_retry(sql, params)` — ejecuta SQL con retry automático (hasta 6 intentos, backoff exponencial: 1s, 2s, 4s, 8s, 16s) si la BD está bloqueada

#### `core/db/content.py` — CRUD de contenidos
- `save_content_to_db()` / `get_content_ref()` / `delete_content_from_db()`

#### `core/db/downloads.py` — Cola de descarga
- `update_queue_status()` / `queue_find_active()` / `queue_insert()` / `queue_get_status()`

#### `core/db/library.py` — Estado de series y actualizaciones
- `set_series_status()` / `get_series_status()` / `get_all_series_statuses()`
- `get_series_to_check()` / `mark_series_checked()` / `get_last_checked()`
- `set_series_updates()` / `get_series_with_updates()` / `clear_series_updates()`

#### `core/db/progress.py` — Progreso de usuario
- `get_progress()` / `save_progress()` / `get_recent_progress()` — get_progress retorna `(chapter, progress)`, save_progress hace upsert con `updated_at`, get_recent_progress retorna las 10 series más recientes con progreso (solo `local:*`)

#### `core/db/settings.py` — Configuración de fuentes
- `get_source_settings()` / `update_source_settings()` / `get_enabled_source_names()` / `ensure_source_in_db()`

#### `core/db/watched.py` — Capítulos vistos
- `mark_chapter_as_watched()` / `is_chapter_watched()` / `get_watched_chapters()` — get retorna lista de strings de chapter_number
- `delete_watched_chapter()` / `delete_watched_chapters_batch()` — batch usado por delete-watched para limpiar en una sola query

---

### `core/disk_cache.py` — Caché en disco

Clase `DiskCache` con:

- Clave hasheada con MD5 + namespace (evita colisiones)
- TTL por entrada (configurable por instancia)
- Escritura atómica (temp → rename)
- `get(key)` → devuelve valor o `None` si expirado
- `set(key, value, ttl?)` → guarda con expiración (override por llamada)
- `aget(key)` / `aset(key, value, ttl?)` → versiones async que usan `asyncio.to_thread()`
  para no bloquear el event loop (usadas por los endpoints async de búsqueda)
- `evict_expired()` → elimina entradas vencidas
- `delete(key)` / `clear()` → limpieza manual

Instancias preconfiguradas:

| Instancia | TTL | Namespace | Uso |
|-----------|-----|-----------|-----|
| `search_cache` | 30 min | `'search'` | Caché de resultados de búsqueda y catálogos |
| `details_cache` | 1 h | `'details'` | Caché de detalles de series |
| `chapters_cache` | 30 min | `'chapters'` | Caché de listas de capítulos |

---

### `core/download_worker.py` — Workers de descarga

Arquitectura productor-consumidor con `Queue(maxsize=50)`:

- `download_queue`: cola threadsafe de jobs (con backpressure, `maxsize=50`)
- `_active_jobs`: dict con `_active_jobs_lock` para jobs en curso
- `_downloading_chapters`: dict con `_dl_lock` para tracking de capítulos en descarga por carpeta
- `_stop_event`: `threading.Event` que permite el graceful shutdown de los workers
- `start_workers(n)`: inicia N hilos daemon (default `DOWNLOAD_NUM_WORKERS` desde config)
- `stop_workers()`: señaliza a los workers que deben terminar

Cada worker:
1. Toma un job de la cola (con timeout de 1 s para poder detectar `_stop_event`)
2. Resuelve capítulos a descargar (`_resolve_chapters` — UNA llamada HTTP)
3. Crea carpeta de destino (`normalize_title`)
4. Descarga portada, genera thumbnail WebP (`thumb.webp` a 200px via ffmpeg) y guarda `series_info.json` (`_save_series_metadata`)
5. Itera capítulos llamando a `source.download_chapter_sync()` con 2 reintentos y backoff exponencial (2s, 4s)
6. Actualiza progreso en BD con frecuencia regulada (flush cada 30 s, en vez de cada N capítulos)
7. Ejecuta `ffmpeg -movflags +faststart` en archivos de video (`_post_process_video`)
8. Marca completado e invalida el índice de series

**Nota:** el worker usa siempre los métodos `_sync` (`get_details_sync`, `get_chapters_sync`, `download_chapter_sync`) para evitar el overhead de `asyncio.to_thread()` dentro de un hilo que ya es síncrono. Cada worker tiene su propio session HTTP (via `HttpPool.get_session()` o `HttpPool.get_scraper()`).

**Lock de descargas activas:** `_downloading_chapters: dict[str, set[str]]` mapea serie → conjunto de capítulos
en descarga. Funciones thread-safe `mark_downloading(series_folder, chapter)`, `unmark_downloading(...)`,
`is_downloading(...)` protegidas por `_dl_lock` previenen que `api_delete_watched` y `api_delete_chapter` eliminen archivos
mientras el worker los está escribiendo. El lock es en memoria y se pierde al reiniciar.

---

### `core/http_pool.py` — Pool HTTP compartido

Gestiona sesiones HTTP usando `threading.local()` para dar a cada hilo su propia
`requests.Session()` y `cloudscraper.CloudScraper`:

- `HttpPool.get_session()` → `requests.Session` thread-local con `pool_connections=20`, `pool_maxsize=40`, `max_retries=2`
- `HttpPool.get_scraper()` → `cloudscraper.CloudScraper` thread-local montado sobre el mismo pool
- `HTTP_TIMEOUT = 30` — timeout global para todas las peticiones

Reduce conexiones abiertas, reutiliza TCP y evita crear 4+ scrapers al arrancar.

**Fix de thread-safety:** anteriormente las sesiones eran variables de clase compartidas
entre todos los hilos. `requests.Session` no es thread-safe, por lo que los workers de
descarga concurrentes podían corromper el estado interno del pool. Con `threading.local()`
cada hilo obtiene su propia sesión sin bloqueos adicionales.

---

### `core/sources.py` — Registro y auto-descubrimiento de fuentes

`discover_sources()` escanea automáticamente el directorio `sources/` en busca de
subclases de `BaseSource`. Cada subclase debe definir `type` (categoría) y `label`
(nombre legible) como atributos de clase. El módulo importa todos los `.py` del
directorio (excluyendo `__init__.py`, `common.py` y módulos marcados con `'--- IGNORE ---'`)
y reúne instancias en un diccionario. También inicializa el sistema de salud para cada fuente.

```python
# Estructura resultante (auto-descubierta — varía según fuentes cargadas):
SOURCES = {
    'anime': {'jkanime': JkanimeSource()},
    'manga': {'nartag': NartagSource(), 'manhwaweb': ManhwawebSource(), 'ikigai': IkigaiSource()}
}
# Después se cargan scrapers dinámicos desde core/scraper_config.py bajo SOURCES['dynamic']
ALL_SOURCES_META = [{'name': 'jkanime', 'type': 'anime', 'label': 'JKanime'}, ...]
```

Funciones:
- `_discover_sources()` → escanea y registra fuentes (se ejecuta al importar el módulo)
- `register_dynamic_source(name)` → importa un módulo `sources.{name}` y registra cualquier subclase de `BaseSource`
- `sync_source_settings()` → sincroniza `ALL_SOURCES_META` + configs dinámicas con la tabla `source_settings` en BD
- `get_source(type, name)` → devuelve instancia o `None`
- `get_all_sources_meta()` → devuelve `list[dict]` con `{type, name, label}` para el frontend
- `get_enabled_sources(type)` → devuelve dict filtrado por `get_enabled_source_names()` en BD, excluyendo fuentes temporalmente desactivadas por fallos

---

### `core/throttle.py` — Rate limiter

Per-domain rate limiter con algoritmo **token bucket**. Espera un mínimo de 2 segundos entre requests al mismo dominio.

- `wait(url)` — versión sync con `threading.Event.wait(timeout=remaining)` (sin busy-wait)
- `async_wait(url)` — versión async con `asyncio.sleep(remaining)`
- `_get_remaining(domain)` — devuelve segundos restantes hasta la próxima llamada permitida

Ambas versiones comparten el mismo `threading.Lock` y diccionario `_last_calls` para evitar race conditions. Usa `urlparse` para extraer el netloc. Instancia global `rate_limiter` con `min_interval=2.0`.

---

### `core/scraper_config.py` — Scrapers dinámicos

Gestiona scrapers definidos por el usuario (sin código) a través de configuración JSON:

- **Carga**: `load_dynamic_sources()` se invoca en `core/sources.py` tras el auto-descubrimiento. Lee la tabla `scraper_configs` de la BD, genera dinámicamente módulos Python en `sources/` que heredan de `DynamicSource` y los registra en `SOURCES`.
- **Validación**: `validate_config(config)` checkea que la configuración tenga estructura válida (selectores, URL, tipo de contenido).
- **CRUD**: `create_config(name, type, label, base_url, config)` guarda en BD y genera stub Python; `update_config(name, ...)` actualiza y regenera si es necesario (si se modifica un built-in, pierde la flag `built_in`); `delete_config(name)` elimina de BD y borra el archivo fuente (built-in no se pueden eliminar); `get_config(name)`, `get_all_configs()`.
- **Persistencia en disco**: `_generate_source_file()` escribe un stub Python en `sources/{name}.py` usando `DYNAMIC_STUB_TEMPLATE`.
- **Test**: `test_config(config, url)` ejecuta el scraper dinámico contra una URL real para verificar que los selectores funcionan.

Los usuarios definen scrapers desde el frontend mediante el wizard de 6 pasos en `settings.html`.

---

### `core/scraper_health.py` — Salud de scrapers

Sistema de monitoreo de fallos por scraper con cooldown automático:

- **Detección de fallos**: `record_failure(name, error_msg)` incrementa contador de fallos consecutivos. Al alcanzar `MAX_FAILURES` (3), desactiva temporalmente el scraper durante `COOLDOWN_SECONDS` (300 s / 5 min).
- **Recuperación**: `record_success(name)` resetea el contador de fallos y registra recuperación si estaba fallando.
- **Consulta**: `is_available(name)` verifica si un scraper está disponible (re-habilita automáticamente tras el cooldown).
- **Re-habilitación manual**: `re_enable(name)` fuerza la re-habilitación de un scraper desactivado.
- **Estado**: `get_status(name)` y `get_all_status()` devuelven el estado de cada scraper (fallo actual, tiempo restante de cooldown, último error).
- **Limpieza**: `clear_source_health(name)` elimina el registro de salud de una fuente (útil al eliminar un scraper dinámico).
- **Inicialización**: `init_health_for_source(name)` crea entrada vacía si no existe.

Usado por `core/sources.py` para filtrar fuentes temporalmente desactivadas y por `api/scraper_tester.py` para exponer el estado vía `/api/scraper-health`.

---

### `core/html_utils.py` — Utilidades de parsing HTML

Funciones reutilizadas por múltiples scrapers y por el sistema de auto-detección:

- `validate_css_selector(selector)` — valida selectores CSS parseándolos con BeautifulSoup
- `extract_items_with_templates(soup, selector, deduplicate_href)` — extrae elementos por selector CSS, incluyendo los ocultos dentro de `<template>` tags (para sitios con patrón "load more"). Deduplica por href para evitar duplicados.
- `normalize_image_url(url, base_url)` — normaliza URLs de imagen y filtra placeholders (1x1, spinner, data:image, etc.)
- `extract_images_from_noscript(soup)` — extrae imágenes de dentro de tags `<noscript>` (lazy-loading)
- `extract_images_from_scripts(soup, base_url)` — extrae URLs de imágenes desde bloques JavaScript (`ts_reader`, `window.__INITIAL_STATE__`, variables `images = [...]`, WordPress madara, Qwik JSON)
- `extract_background_images(soup, selector)` — extrae URLs de CSS `background-image`
- `extract_from_srcset(element)` — extrae la imagen más grande de un atributo `srcset`
- `normalize_url(url, base_url)` — normaliza URLs relativas
- `url_ext(url, default)` — extrae extensión de imagen de una URL

Constantes: `ATTR_PRIORITY` (orden de atributos de imagen a intentar) y `SKIP_URL_PATTERNS` (patrones a filtrar).

---

### `core/chapter_utils.py` — Utilidades de capítulos

Funciones para normalizar y manejar capítulos decimales (ej. `"5.5"`):

- `normalize_chapter_number(num)` — elimina ceros a la izquierda (ej. `"005.5"` → `"5.5"`)
- `chapter_float_key(num)` — clave de ordenamiento para sorting de capítulos (retorna `float` o `0.0` si no es numérico)
- `chapter_to_filename(num, padding)` — convierte `"5.5"` → `"0005_5"` para nombres de archivo/carpeta
- `parse_chapter_from_filename(name)` — extrae el número de capítulo de un nombre de archivo (ej. `"serie_005_5"` → `"5.5"`, `"serie_005"` → `"5"`)

---

### `core/selector_detector.py` — Inferencia de selectores

Analiza HTML de sitios upstream para sugerir selectores CSS automáticamente:

- **`detect_search_selectors(html, url)`**: dado el HTML de una página de búsqueda/results, encuentra elementos que contienen enlaces, imágenes y títulos. Devuelve hasta 3 selectores candidatos rankeados por confianza.
- **`detect_detail_selectors(html, url)`**: analiza página de detalle de serie para inferir selectores de portada, sinopsis, géneros.
- **`detect_chapter_selectors(html, url)`**: analiza página de capítulos para inferir selectores de ítem, número y enlace.
- **`detect_selector_by_text(html, text, stage, base_url)`**: dado un texto visible que el usuario sabe que existe en la página, busca elementos que lo contengan y sugiere selectores para la etapa indicada (`search`, `details`, `chapters`, `content`). Para el stage `content` usa 5 estrategias de fallback: (1) `<img>` regular, (2) imágenes en `<noscript>`, (3) URLs desde scripts JS, (4) CSS `background-image`, (5) cualquier `<img>` con URL válida. Detecta lazy-loading: si un `<img>` tiene `src=""` y `data-src` poblado (o clases `page-img-lazy`, `lazy`, `lozad`), sugiere `data-src` como atributo.
- **`_find_elements_by_text(soup, text)`**: helper que busca nodos de texto que contengan el texto exacto, rankeando por puntuación de coincidencia exacta.
- **`_find_parent_card(element, card_tags)`**: helper que asciende en el DOM hasta encontrar un contenedor que coincida con los tags de card típicos.

Usa heurísticas como: elementos `<a>` con href, imágenes con `src` o `data-setsrc`, patrones de clase comunes, búsqueda por texto visible. Es usado por `POST /api/scraper-configs/auto-detect` y `POST /api/scraper-configs/detect-selectors` para guiar al usuario en la creación de scrapers dinámicos.

---

### `core/utils.py` — Utilidades

- `normalize_title(raw)` — limpia títulos para nombres de carpeta (ASCII, sin acentos, sin caracteres especiales, max 100 chars)
- `_normalize_path_name(text)` — normalización para comparación de rutas
- `normalize_for_comparison(text)` — solo alfanuméricos, minúsculas, sin tildes
- `scan_downloaded_series()` — escanea `ANIME_DOWNLOAD_DIR` y `MANGA_DOWNLOAD_DIR` y devuelve lista de series enriquecida con progreso desde BD. Usa `ThreadPoolExecutor(8)` para paralelizar la lectura de `series_info.json` y una sola query SQL (LEFT JOIN) en vez de N+1 contra BD. La caché del resultado dura 300s (5 min) con invalidación por generación.
- `count_images_in_dir(cap_dir)` — cuenta archivos de imagen (.jpg/.jpeg/.png/.webp) en un directorio de capítulo
- `_get_image_dimensions_from_bytes(data)` — extrae dimensiones (ancho × alto) de bytes raw de imagen sin decodificar completa. Soporta PNG (IHDR), JPEG (SOF0/SOF2), WebP (VP8/VP8L), GIF y BMP. Devuelve `(width, height)` o `None`.
- `filter_manga_images(image_urls, min_dimension=300, max_workers=16)` — filtra URLs de imágenes de manga descargando solo los primeros 32KB de cada una (headers) para leer dimensiones. Usa `stream=True` con `iter_content` para no descargar imágenes completas. Verifica en paralelo (16 workers) con rate limiting por dominio. Devuelve solo URLs donde ancho **y** alto ≥ `min_dimension`. Las imágenes que no se pueden parsear se mantienen por defecto (seguridad).

---

### `sources/__init__.py` — BaseSource

Clase abstracta que define el contrato de todas las fuentes usando modelos Pydantic (`core/models.py`).

Cada subclase debe definir atributos de clase `type` (categoría: `"anime"`|`"manga"`)
y `label` (nombre para mostrar en UI). Estos son usados por `discover_sources()` para
el registro automático y por el frontend para el menú desplegable de fuentes.

Cada método tiene una versión **sync** (`*_sync`) y una **async** (el mismo nombre sin sufijo). Por defecto, la versión async delega a la sync mediante `_run_in_executor()` con un `ThreadPoolExecutor(max_workers=4)` compartido por instancia de fuente (acotado, evita crear un hilo por llamada).

Las subclases pueden sobreescribir la versión async para implementaciones nativamente async.

| Método sync | Método async | Retorno | Descripción |
|-------------|--------------|---------|-------------|
| `search_sync(query)` | `search(query)` | `list[SearchResult]` | Busca por título |
| `get_details_sync(id)` | `get_details(id)` | `SeriesDetails` | Portada, sinopsis, tipo, género |
| `get_chapters_sync(id)` | `get_chapters(id)` | `list[Chapter]` | Capítulos con `{number, id}` |
| `download_chapter_sync(id, chapter_id, dest)` | `download_chapter(id, chapter_id, dest)` | `str` | Descarga un capítulo, devuelve ruta |
| `get_stream_url_sync(id, chapter_id)` | `get_stream_url(id, chapter_id)` | `str\|None` | URL directa para streaming (solo anime) |
| `get_chapter_images_sync(id, chapter_id)` | `get_chapter_images(id, chapter_id)` | `list[str]` | URLs de imágenes para streaming (solo manga) |
| `warm_cache_sync()` | `warm_cache()` | `None` | Precarga catálogo en background (opcional) |

Además, la propiedad `supports_streaming` (bool) indica si la fuente puede transmitir
contenido en streaming. Por defecto `False` en `BaseSource`. `JkanimeSource` lo
sobrescribe a `True`. `DynamicSource` retorna `True` solo si `content_type == 'video'`.
Usado por `routers/pages.py` para decidir si mostrar el botón "Reproducir" en la
página de serie para fuentes no locales.

**Soporte de capítulos decimales:**
- Todas las fuentes usan `chapter_to_filename(chapter.number)` para nombres de carpeta/archivo en vez de `int(float(...))`, permitiendo capítulos como `"5.5"` que se guardan como `0005_5`
- Se eliminó el filtro `float(num) != int(float(num))` que descartaba capítulos decimales en ikigai, nartag, manhwaweb y jkanime
- jkanime corrigió su clave de ordenamiento de `int(x.number)` a `float(x.number)`

**Uso:**
- La API FastAPI (async) llama a los métodos async (`await source.search(...)`)
- Los download workers (hilos) llaman a los métodos sync (`source.search_sync(...)`)

---

### `sources/common.py` — Mixin HTTP y helpers de manga

Dos clases reutilizables por todos los scrapers:

- **`HttpClientMixin`**: mixin que provee métodos HTTP con rate limiting y retry:
  - `__init__()` obtiene un `cloudscraper.CloudScraper` de `HttpPool` (thread-local)
  - `_get(url, referer?)` — GET con headers y rate limiter
  - `_post(url, data?, referer?)` — POST con headers (incluye `X-Requested-With: XMLHttpRequest`)
  - `_get_json(url)` — GET con parseo JSON (incluye `Accept: application/json`)
  - `_get_with_retry(url, retries=3, backoff=1.0)` — GET con reintento exponencial
- **`MangaDownloadHelper`**: helpers estáticos para descarga de manga:
  - `count_images(cap_dir)` — cuenta archivos de imagen (.jpg/.jpeg/.png/.webp) en un directorio
  - `make_chapter_dir(dest, chapter_number)` — crea carpeta del capítulo (`cap_0005_5`)
  - `download_images(img_urls, cap_dir, headers, retry_get)` — descarga imágenes secuencialmente, retorna número de fallos. Skips archivos existentes.

---

### `sources/jkanime.py` — JKanime (anime)

Scraper de `jkanime.net`:

- **Búsqueda**: scraping HTML con BeautifulSoup (cards `.anime__item`)
- **Detalles**: scraping de página de serie (portada, sinopsis)
- **Capítulos**: AJAX endpoint `/ajax/episodes/{serie_id}/{page}` con paginación. Primero intenta GET, fallback a POST.
- **Streaming**: decodifica base64 para obtener URLs de servers embed, extrae URL directa vía iframe. Propiedad `supports_streaming = True`.
- **Descarga**: prioridad de servidores: Mediafire → Mp4upload → Mega → Streamwish → VOE → Vidhide → Mixdrop → Streamtape → Doodstream. Usa `_download_stream()` o `_download_curl()` (con resume `-C -` y verificación de Content-Length).
- **Cache**: catálogo no, solo detalles y capítulos por serie

---

### `sources/nartag.py` — Nartag (manga)

Scraper de `nartag.com` (reader en `lector.nartag.com`):

- **Autenticación**: POST con form redirect (`rk_madara_redirect`) para bypass anti-bot, luego POST a `/wp-json/rk/v1/authorize`
- **Búsqueda**: WordPress search (`?s={query}&post_type=wp-manga`), parsea cards `.tab-thumb.c-image-hover`
- **Detalles**: scraping de `/manga/{content_id}/`
- **Capítulos**: AJAX POST a `/manga/{content_id}/ajax/chapters/`, regex extrae slugs
- **Streaming**: `get_chapter_images_sync()` navega el flujo de autorización del reader y extrae URLs de imágenes, filtrando por dominio y path
- **Descarga imágenes**: usa `get_chapter_images_sync()` y luego descarga con `MangaDownloadHelper`
- **Cache**: catálogo completo (TTL 3 días), detalles y capítulos por serie

---

### `sources/manhwaweb.py` — ManhwaWeb (manga)

Scraper de `manhwaweb.com` (backend en Railway):

- **Búsqueda**: API backend (`/manhwa/library?buscar={query}`) con fallback a scraping HTML
- **Detalles**: API (`/manhwa/see/{content_id}`) + scraping
- **Capítulos**: API (campo `chapters[]`) + scraping de enlaces `/leer/`
- **Streaming**: `get_chapter_images_sync()` obtiene URLs de imágenes vía API (`/chapters/see/{chapter_id}`) o scraping
- **Descarga imágenes**: usa `get_chapter_images_sync()` y luego descarga por lotes con retry (3 intentos, backoff exponencial)
- **Cache**: catálogo completo (TTL 3 días), detalles y capítulos por serie
- **Background**: `warm_cache()` + `_refresh_catalog_background()` en daemon threads

---

### `sources/ikigai.py` — VisorIkigai (manga)

Scraper de `ikigai.yomod.xyz`:

- **Búsqueda**: catálogo completo desde API con paginación paralela (4 workers, max 500 páginas). Búsqueda por substring sobre el catálogo cacheado.
- **Detalles y capítulos**: scraping de `/series/{content_id}/` con paginación de capítulos
- **Streaming**: `get_chapter_images_sync()` extrae URLs de imágenes vía scraping, fallback a Qwik JSON (`<script type="qwik/json">`)
- **Descarga imágenes**: usa `get_chapter_images_sync()` y luego descarga secuencial
- **Cache**: catálogo completo (TTL 3 días), detalles (1h) y capítulos (30 min)
- **Background**: `warm_cache()` precarga catálogo en daemon thread con cooldown de 24h entre refrescos
- Usa `cloudscraper` para bypass de Cloudflare

---

### `sources/dynamic.py` — Motor de scrapers dinámicos

Clase `DynamicSource` que hereda de `BaseSource` y ejecuta scrapers definidos por configuración JSON (sin código):

- **Configuración**: recibe un dict con `search_selector`, `detail_selectors`, `chapter_selectors`, `content_type`, etc.
- **Búsqueda**: usa `soup.select(config['search_selector'])` para extraer resultados. También inspecciona `<template>` tags para sitios con patrón "load more" (deduplica por `href`). Soporta ambos métodos HTTP (GET/POST) según configuración.
- **Catálogo**: si `has_catalog = true`, `search_sync()` construye el catálogo completo desde `catalog_url_template` (paginado con `{page}`, stop cuando una página devuelve 0 items o se alcanza `catalog_max_pages`). El catálogo se cachea con `DiskCache` (TTL configurable vía `catalog_cache_ttl`). La precarga se lanza en `warm_cache_sync()` con un lock por fuente para evitar refrescos concurrentes (cooldown de 24 h). La búsqueda por query filtra localmente sobre el catálogo cacheado.
- **Detalles**: extrae portada, sinopsis y géneros según selectores configurados.
- **Capítulos**: extrae lista numerada de capítulos desde selectores CSS, soporta paginación.
- **Streaming/descarga**: según `content_type` (`image` o `video`):
  - `image`: extrae URLs de imágenes con 6 estrategias de fallback: (1) CSS selector + atributo configurado, (2) selector + todos los atributos prioritarios, (3) extracción de `<noscript>`, (4) URLs desde scripts JS, (5) CSS `background-image`, (6) cualquier `<img>` con atributo src-like. El atributo por defecto es `src`, pero puede configurarse a `data-src` para sitios con lazy loading.
  - `video`: extrae una URL de video con `content_video_selector` + `content_video_attr`.
- **Propiedad `supports_streaming`**: retorna `True` solo si `content_type == 'video'`, usado por el frontend para mostrar el botón de reproducción.
- **Errores**: trackea el último error por config (`_set_error`/`_clear_error`), expuesto vía `get_last_error(name)`.
- **Cache**: usa `search_cache` con TTL por defecto.

Las instancias son creadas por `core/scraper_config.py` y registradas automáticamente en `SOURCES['dynamic']`.

---



## Frontend

### Templates Jinja2

Herencia: `base.html` → `{index, serie, reader, settings}.html`

El proyecto usa **build en dos modos**:

- **Producción** (`python3 scripts/build.py`): genera bundles minificados con content hash en `static/dist/`. `routers/pages.py` carga el manifiesto (`build.json`) y lo pasa al contexto Jinja2 como `{{ bundles }}`. Cada template carga un único CSS + JS por página.
- **Desarrollo** (sin build): los templates cargan los archivos individuales como fallback, permitiendo editar CSS/JS sin recompilar.

- **`base.html`**: layout raíz. En producción carga preload hints para Inter y FA subset. En desarrollo carga `inter.css`, `fa-subset.css`, `base.css`, `layout.css`. Siempre incluye `api.js` (síncrono) y en desarrollo carga `toast.js`, `confirm.js`, `queue-indicator.js`, `scraper-health.js`. Helpers inline de modal y animación de cards (IntersectionObserver).
- **`index.html`**: dos paneles (Anime / Manga) con pestañas, búsqueda por fuente (dropdown dinámico que solo muestra fuentes habilitadas), botón de engranaje para abrir popup de configuración de fuentes, biblioteca local con filtros por estado. Carga `bundles.css_index` + `bundles.js_index` (o `index.css` + `app.js` en dev).
- **`serie.html`**: portada con parallax, sinopsis expandible, lista de capítulos con botones de play/download/watched, badge de actualizaciones. Recibe `canStream` desde el backend vía `window.serieData`. Carga `bundles.css_serie` + `bundles.js_serie`.
- **`settings.html`**: wizard de 6 pasos para crear scrapers dinámicos. Cada paso corresponde a una etapa del scraper: (1) nombre/tipo/URL base, (2) búsqueda con toggle de catálogo, (3) detalles, (4) capítulos, (5) contenido (imagen o video), (6) resumen. Incluye campos de texto de muestra y botones "Detectar" en cada paso para auto-detección por texto visible. La sección avanzada (selectores CSS) es colapsable y editable para override manual. Carga `bundles.css_settings` + `bundles.js_settings`.
- **`reader.html`**: reproductor de video o visor de manga a pantalla completa. Carga `bundles.css_reader` + `bundles.js_reader`.

### CSS — Design system

- **`base.css`**: tokens (`:root`), reset, componentes reutilizables (buttons, cards, modal, spinner, progress bar, scrollbar, animaciones). Incluye clases extraídas de inline styles: `.card-dl-btn`, `.resume-btn`, `.status-tag-btn`, `.card-actions-row`, `.card-chips-nowrap`, `.chip-sm`.
- **`layout.css`**: navegación sticky con blur, estructura de página, responsive breakpoints
- **`index.css`**: filtros de biblioteca tipo chip con scroll horizontal en móvil
- **`serie.css`**: efecto parallax en cover, hero card, expansión de sinopsis, clase `.back-link`
- **`reader.css`**: layout full-screen, barra de controles, botones de navegación
- **`settings.css`**: wizard de scrapers dinámicos: secciones `.detect-section` para entrada de texto de muestra, `.step-indicator` para los 6 pasos, toggles de sección avanzada y catálogo
- **`inter.css`**: define `@font-face` para Inter en woff2 (pesos 400, 500, 600, 700, 800). Los archivos TTF originales fueron eliminados.
- **`fa-subset.css`**: subset de Font Awesome Free con solo los 28 iconos realmente usados. Incluye `@font-face` apuntando a `fa-solid-900-subset.woff2`. Se usa tanto en desarrollo como en producción.

### JavaScript

- **`api.js`**: wrapper HTTP global con `window.api`. GET con dedup de requests inflight (misma URL comparte Promise), POST, PUT y DELETE. Maneja errores parseando `detail` o `error` del body JSON.
- **`app.js`**: tabs (Anime/Manga/Biblioteca), búsqueda con SSE streaming (`/api/search-all-stream`), biblioteca con filtros por estado, notificaciones toast, popup de estado, configuración de fuentes (icono engranaje → popup con checkboxes para activar/desactivar fuentes). Usa `CoverObserver` dual (IntersectionObserver) para lazy-load y liberación de imágenes fuera de viewport. Renderizado diferencial de la biblioteca (solo actualiza nodos cambiados).
- **`serie.js`**: carga de capítulos, descarga individual/completa, marcado como visto (watched), detección de actualizaciones. Progreso visible tanto para contenido local como remoto. Virtualización de pills de capítulos (batches de 30 con IntersectionObserver). Patch in-place del DOM para estado watched/downloaded.
- **`reader.js`**: reproductor de video con guardado de progreso cada 15s, auto-marca visto al 99%. Visor de manga con scroll virtual (binary search + prefix sums), precarga proactiva de imágenes (`_prefetchNextBatch`) — carga hasta 3 imágenes más allá de la ventana actual con delay progresivo de 200ms. Filtrado de imágenes pequeñas en cliente: imágenes con `naturalWidth` o `naturalHeight < 300px` se colapsan a `height: 0` (complementa el filtro server-side en `filter_manga_images`). Corrección de scroll inicial (`_fixInitialScroll`): espera a que todas las imágenes de la ventana inicial decodifiquen, recalcula la posición de scroll con alturas reales (no estimaciones de 1200px), y fuerza re-montaje de la ventana. Guarda progreso en BD tanto para contenido local como remoto. Atajos de teclado (Space, F, C, Left/Right arrows).
- **`settings.js`**: wizard de 6 pasos para crear/editar scrapers dinámicos. Incluye: campos de texto de muestra + botón "Detectar" por cada paso (usa `detectByText()` que llama a `/api/scraper-configs/detect-selectors`), toggle de catálogo con campos específicos, `getCatalogConfig()`, `toggleCatalogSection()`. Maneja la creación, edición y guardado de configuraciones con draft en localStorage.
- **`queue-indicator.js`**: indicador flotante de descargas activas con popup de progreso. Usa `BroadcastChannel` (`anyone:queue`) para coordinación cross-tab. Polling cada 2-5s cuando hay jobs activos, se detiene en idle.
- **`scraper-health.js`**: indicador de salud de scrapers (top-left). Muestra fuentes con errores o desactivaciones temporales. Botón "Re-enable" para recuperar. Usa `BroadcastChannel` (`anyone:health`) para sync cross-tab. Respeta el toggle `localStorage.anyone_hide_scraper_errors`.
- **`toast.js`**: notificaciones toast (éxito/error/info) con auto-dismiss y stack en bottom-right.
- **`confirm.js`**: diálogo de confirmación global basado en Promise. Resuelve `true`/`false` según botón clickeado.

---

## Flujo de datos típico

### Búsqueda
```
Usuario escribe "naruto" → JS llama GET /api/search/anime/jkanime?q=naruto
  → api/search.py (async def) await source.search(query)
    → BaseSource.search() ejecuta search_sync() via asyncio.to_thread()
      → scraper hace HTTP a jkanime.net, parsea HTML (sin bloquear event loop)
  → api/search.py enriquece resultados con estado de BD (descargado, progreso)
→ JS renderiza grid de resultados
```

### Descarga
```
Usuario hace clic en "Descargar serie completa"
  → JS POST /api/download {type, source, content_id, title}
    → api/downloads.py encola job en download_queue (SQLite)
  → Worker (hilo) toma el job:
       1. get_chapters_sync() → lista remota (llamada sync directa)
       2. Crea carpeta: /Descargas/Manga/naruto/
       3. Descarga portada + series_info.json
       4. Por cada capítulo: download_chapter_sync() → imágenes
       5. Actualiza progreso en BD
   → JS polling a GET /api/queue para mostrar progreso
```

### Actualizaciones automáticas
```
Scheduler (daemon thread, cada 24h):
  → POST /api/library/check-all-updates
    → api/updates.py consulta series con status 'watching'/'completed'
    → Por cada serie: obtiene solo capítulos remotos posteriores al máximo local (optimización)
    → Si hay nuevos: guarda en series_status.new_chapters_found
    → El frontend muestra badge en la serie
```

---

## Frontend Build System

### `scripts/build.py`

Script de build en Python puro (sin Node.js) que:

1. **Escanea** `static/css/*.css` y `static/js/*.js` en busca de los archivos fuente.
2. **Agrupa por página**: para cada template (`index`, `serie`, `reader`, `settings`) concatena su CSS específico con el CSS común (`inter.css`, `fa-subset.css`, `base.css`, `layout.css`). Lo mismo con JS: `index` y `serie` obtienen `toast + confirm + queue-indicator + scraper-health + app/serie`; `reader` obtiene solo `reader.js`; `settings` obtiene `toast + confirm + settings`.
3. **Minifica**: usa `cssmin` para CSS y `jsmin` para JS (con fallback graceful si no están instalados).
4. **Hashea**: calcula SHA-256 del contenido minificado y lo trunca a 12 caracteres para el nombre del archivo (ej. `index.a1b2c3d4e5f6.css`).
5. **Genera manifiesto**: escribe `static/dist/build.json` con la correspondencia lógica → nombre real.
6. **Limpia**: elimina archivos huérfanos en `dist/` que ya no correspondan a ninguna entrada del manifiesto.

**Uso:**
```bash
python3 scripts/build.py
```

### Integración con Jinja2 y caché

`routers/pages.py` lee `build.json` al arrancar y lo inyecta en el contexto de Jinja2 como `{{ bundles }}`. Cada template usa:

```jinja
{% if bundles %}
<link rel="stylesheet" href="/static/dist/{{ bundles.css_index }}">
<script src="/static/dist/{{ bundles.js_index }}" defer></script>
{% else %}
<link rel="stylesheet" href="/static/css/index.css">
<script src="/static/js/app.js" defer></script>
{% endif %}
```

Además, en producción se emiten **preload hints** para los font files críticos y se agregan headers de caché agresivos (`Cache-Control: public, max-age=31536000, immutable`) a través de la clase `CachedStaticFiles` en `app.py` para toda la carpeta `/static/dist/`.

### Cache headers

En `app.py` (clase `CachedStaticFiles`) se configuran dos niveles de caché:

| Ruta | Cache-Control | Estrategia |
|---|---|---|
| `/static/dist/` | `public, max-age=31536000, immutable` | Hasheado, seguro cachear para siempre |
| `/static/` (salvo dist) | `public, max-age=86400` | Sin hash, caché de 1 día |
| `/favicon.ico` | `public, max-age=86400` | Sin hash, caché de 1 día |

## Optimizaciones de Frontend

### Font Awesome Subset (~93% de reducción)

- Se identificaron los iconos realmente usados en templates y JS (28 glifos del set `fa-solid`).
- Se generó un subset usando `fonttools` (`pyftsubset`) desde el TTF original, produciendo `fa-solid-900-subset.woff2` (~2.5KB vs ~35KB del original).
- Se creó `fa-subset.css` con `@font-face` apuntando al subset.
- **Flujo de generación** (documentado en `docs/fontawesome-subset.md`):
  ```bash
  pyftsubset fa-solid-900.ttf \
    --unicodes="f013,f0ac,f02d,f045,f067,f068,f071,f077,f07b,f07c,f08b,f0a0,..." \
    --output-file=fa-solid-900-subset.ttf \
    --layout-features=''
  # luego convertir TTF → woff2 con google/woff2
  ```
- El CSS original `fontawesome.min.css` y las fuentes TTF se eliminaron por no usarse. Solo se usa `fa-subset.css` en todos los entornos.
- Se corrigió `queue-indicator.js` para usar `fa-arrow-down` (`f063`) en vez de `fa-arrow-down-to-line` (inexistente en FA6 Free, causaba icono fantasma).

### Inter — conversión TTF → woff2 (65% de reducción)

- Los 6 pesos TTF originales (~1.49 MB total) se convirtieron a woff2 (~523 KB total) usando `google/woff2`. Los TTF originales fueron eliminados.
- El peso 300 fue eliminado por no estar referenciado en ningún `font-family` ni template.
- `inter.css` solo sirve woff2 (formato `woff2`).

### CSS-in-JS eliminado (~210 líneas de inline styles extraídas)

Se migraron todos los estilos inline de los templates Jinja2 a clases CSS:

| Clase añadida | Propósito | Se usó en |
|---|---|---|
| `.card-dl-btn` | Botón descarga de la card | `index.html` |
| `.resume-btn` | Botón reanudar | `serie.html`, `reader.html` |
| `.status-tag-btn` | Tag de estado clickeable | `index.html` |
| `.card-actions-row` | Fila de acciones de card | `index.html` |
| `.card-chips-nowrap` | Chips sin wrap en card | `index.html` |
| `.chip-sm` | Chip pequeño | `index.html` |
| `.back-link` | Enlace volver | `serie.html` |

Esto eliminó dependencia de estilos inline, redujo el HTML servido y facilitó la reutilización.

### Bundling y minificación

- Cada página recibe exactamente un CSS bundle y un JS bundle (sin duplicación de CSS común). Los bundles de `index`, `serie` y `reader` incluyen `inter.css`, `fa-subset.css`, `base.css` y `layout.css` junto con su CSS específico; `settings` incluye los mismos comunes más `settings.css`.
- Se eliminaron dependencias de librerías externas (Font Awesome inline, etc.) que ya no se necesitaban en producción.
- `build.py` no requiere Node.js ni npm — corre con Python estándar + `cssmin` y `jsmin` (instalables vía pip).
