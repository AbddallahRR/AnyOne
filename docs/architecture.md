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
├── config.py                 → Variables de entorno y rutas
├── requirements.txt          → Dependencias Python
├── pyproject.toml            → Configuración del proyecto (ruff, mypy)
├── Dockerfile                → Imagen Docker (python:3.12-slim)
├── docker-compose.yml        → Orquestación local
│
├── routers/                  → FastAPI routers
│   ├── pages.py              →   Rutas HTML (/, /serie, /reader)
│   └── api/                  →   API REST (/api/*)
│       ├── __init__.py       →   Crea el APIRouter y exporta _check_all_updates_core
│       ├── common.py         →   Helpers compartidos (índice en memoria, cola, fs)
│       ├── settings.py       →   Configuración de fuentes (/api/settings*)
│       ├── search.py         →   Búsqueda en fuentes (/api/search*)
│       ├── content.py        →   Detalle, capítulos y reproducción (/api/content, /api/play)
│       ├── library.py        →   Biblioteca, progreso, etiquetas, vistos
│       ├── downloads.py      →   Cola de descarga (/api/download, /api/queue)
│       ├── updates.py        →   Comprobación de capítulos nuevos
│       └── scraper_configs.py →   CRUD de scrapers dinámicos (/api/scraper-configs/*)
│
├── core/                     → Lógica compartida
│   ├── database.py           →   SQLite (migraciones, progreso, cola, etiquetas)
│   ├── disk_cache.py         →   Caché JSON en disco con TTL
│   ├── download_worker.py    →   Workers en hilos para descarga
│   ├── http_pool.py          →   Pool HTTP compartido (Session + Scraper)
│   ├── models.py             →   Modelos Pydantic (validación, serialización)
│   ├── settings.py           →   Config tipada con pydantic-settings
│   ├── sources.py            →   Registro de fuentes disponibles
│   ├── throttle.py           →   Rate limiter por dominio
│   ├── scraper_config.py     →   Gestión de scrapers dinámicos (carga, validación, persistencia)
│   ├── selector_detector.py  →   Inferencia automática de selectores CSS desde HTML
│   └── utils.py              →   Normalización de títulos, escaneo local
│
├── sources/                  → Scrapers (uno por sitio upstream)
│   ├── __init__.py           →   Clase base BaseSource
│   ├── animeflv.py           →   www3.animeflv.net (anime)
│   ├── jkanime.py            →   jkanime.net (anime)
│   ├── nartag.py             →   nartag.com (manga)
│   ├── manhwaweb.py          →   manhwaweb.com (manga)
│   ├── ikigai.py             →   visorikigai (manga)
│   ├── olympus.py            →   olympusscanlation (manga)
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
    │   ├── Inter-{400,500,600,700,800}.ttf   → Pesos de Inter (TTF, solo dev)
    │   └── Inter-{400,500,600,700,800}.woff2     → Pesos de Inter convertidos a woff2
    ├── webfonts/
    │   ├── fa-solid-900.woff2           → Font Awesome completo (solo dev)
    │   ├── fa-solid-900-subset.woff2    → Subset con solo los 28 iconos usados
    │   ├── fa-regular-400.woff2         → No usado, mantenido por compatibilidad
    │   └── fa-brands-400.woff2          → No usado, mantenido por compatibilidad
    ├── js/
    │   ├── app.js            →   Lógica de index.html
    │   ├── serie.js          →   Lógica de serie.html
    │   ├── reader.js         →   Lógica de reader.html
    │   └── queue-indicator.js →  Indicador flotante de descargas
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

### `config.py` — Configuración (legacy bridge)

Wrapper delgado que re-exporta las variables de `core/settings.py` para compatibilidad
con imports existentes (`from config import ANIME_DOWNLOAD_DIR`).

Exporta todas las variables de `core/settings.py` incluyendo `DOWNLOAD_NUM_WORKERS`
(anteriormente no expuesto, causando que el valor por defecto en `download_worker.py`
siempre cayera a 3).

Toda la lógica de validación y defaults vive ahora en `core/settings.py`.

---

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

Crea automáticamente los directorios en la instanciación mediante `config.py`.

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
- `WatchedToggleRequest`, `ProgressRequest`, `DeleteWatchedRequest`, `DeleteChapterRequest`
- `AcknowledgeUpdatesRequest`, `SearchQuery`

Nota: los campos `chapter` en `WatchedToggleRequest` y `DeleteChapterRequest`, y `excluded_chapters` en `DownloadJob` son de tipo `str` para soportar capítulos decimales (ej. `"5.5"`).

**Modelos de scrapers dinámicos:**
- `ScraperConfigSchema` — schema de configuración de scrapers dinámicos con campos para búsqueda (`search_url_template`, `search_result_selector`, etc.), detalles, capítulos, contenido (`content_type`, `content_image_selector`, `content_image_attr`, `content_video_selector`) y catálogo (`has_catalog`, `catalog_url_template`, `catalog_item_selector`, `catalog_max_pages`, `catalog_cache_ttl`, etc.)

**Modelos internos:**
- `DownloadJob` — job tipado para la cola de descarga

**Helpers de capítulos decimales:**
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
6. Arranca el scheduler de actualizaciones (cada 24 h)
7. Emite warning si `SECRET_KEY` tiene el valor inseguro por defecto
8. Monta `StaticFiles` y registra los routers (`pages`, `api`)
9. Lanza precarga en background de todas las fuentes (`asyncio.create_task(_warm_all_sources())`)
10. Al shutdown: detiene los workers gracefulmente (`stop_workers()`)

La precarga de catálogos (`_warm_all_sources`) ejecuta todos los `warm_cache()` en paralelo
con `asyncio.gather()` y timeout de 30 s por fuente, usando `asyncio.create_task()` en el
event loop principal (anteriormente creaba un segundo event loop en un hilo separado con
`asyncio.run()`, lo que era una anti-patrón).

**Health check:** `GET /health` → `{'status': 'ok'}` para monitoreo del contenedor.

---

### `routers/pages.py` — Rutas HTML

Tres rutas que renderizan templates Jinja2:

| Ruta | Template | Función |
|------|----------|---------|
| `/` | `index.html` | Página principal (búsqueda + biblioteca local) |
| `/serie/<type>/<source>/<id>` | `serie.html` | Detalle de serie y lista de capítulos |
| `/reader/<type>/<source>/<content_id>/<chapter>` | `reader.html` | Lector/reproductor a pantalla completa |
| `/settings` | `settings.html` | Wizard de scrapers dinámicos |

La ruta `/serie` determina si la fuente soporta streaming (`can_stream`) consultando
`src.supports_streaming` en el backend. Para fuentes manga siempre retorna `true`;
para anime depende de que la fuente implemente `get_stream_url()`. El flag se pasa
al template como `window.serieData.canStream` para que el frontend muestre u oculte
el botón "Reproducir en streaming".

---

### `routers/api/` — API REST (paquete)

Antes un solo archivo de ~1180 líneas (Flask), ahora modularizado en 6 submódulos con FastAPI. Corazón del backend.

---

#### `api/common.py` — Helpers compartidos

Funciones y estado global reutilizados por todos los submódulos:

- `_safe_path(base, untrusted)` — previene path traversal
- `_build_series_index` / `_get_series_index` / `_invalidate_series_index` — índice en memoria de series locales (content_id → Path). `_build_series_index` usa `ThreadPoolExecutor(8)` para leer los `series_info.json` en paralelo.
- `_find_local_serie_dir` — busca carpeta por content_id (índice O(1) + fallback por normalización)
- `_local_chapters_anime` / `_local_chapters_manga` — lista capítulos locales
- `_delete_chapter_files` — elimina archivos de un capítulo en disco
- `_resolve_series_title` — resuelve título desde BD o disco
- `_queue_find_active` / `_queue_insert` / `_queue_get_status` — acceso a la cola de descarga
- `_base_folder` / `_get_json` / `_require_local` / `_content_title_by_ref` — utilidades menores

---

#### `api/search.py` — Búsqueda

Todos los endpoints son `async def` y hacen `await` a los métodos async de las fuentes:

- `GET /api/search?type=...&source=...&q=...` — busca en una fuente (con caché + progreso enriquecido). La caché se consulta con `search_cache.aget()` (async) para no bloquear el event loop.
- `GET /api/search-all?type=...&q=...` — busca en todas las fuentes del tipo concurrentemente con `asyncio.gather` + dedup.
- `GET /api/search-all-stream?type=...&q=...` — SSE con resultados progresivos (timeout 90s, cachea para visitas posteriores). Cada fuente se busca con `asyncio.wait_for()`.

---

#### `api/content.py` — Contenido y reproducción

- `GET /api/content/<type>/<source>/<id>` — portada, sinopsis
- `GET /api/chapters/<type>/<source>/<id>` — lista remota de capítulos
- `GET /api/chapters/with-local/<type>/<source>/<id>` — remotos marcando descargados
- `GET /api/content/local/<type>/<id>` — detalle de contenido local
- `GET /api/chapters/local/<type>/<id>` — capítulos locales en disco
- `GET /api/local-cover/<type>/<path:filename>` — sirve portada local (soporta `?thumb=1` para thumbnail WebP, con `Cache-Control` y `ETag` para caché HTTP)
- `GET /api/play/<type>/<source>/<id>/<chapter>` — sirve video local (legacy)
- `GET /api/play/local/<type>/<id>/<chapter>` — reproducción local, soporta `chapter` como string para decimales (busca archivos con `_` como separador decimal, ej. `serie_005_5.mp4`)
- `GET /api/play/remote/<type>/<source>/<id>/<chapter>` — streaming remoto: anime → redirect 307 a CDN, manga → JSON con URLs de imágenes
- `GET /api/manga/images/<path:subpath>` — imágenes de manga (con `Cache-Control: max-age=86400` y `ETag` para 304 Not Modified)
- `GET /api/video-duration/anime/<id>/<chapter>` — duración del video con ffprobe (cached 24 h)

---

#### `api/library.py` — Biblioteca, progreso, etiquetas, vistos

- `GET /api/library` — lista de series descargadas
- `GET/POST /api/library/status` y `GET /api/library/status/<ref>` — etiquetas (watching/completed/pending/none)
- `GET/POST /api/progress/<type>/<source>/<id>` y `/progress/local/<type>/<id>` — progreso de usuario. Funciona para cualquier `content_ref` ("fuente:id"), tanto local como remoto. El progreso se guarda automáticamente desde `reader.js` (cada 15 s para video, al hacer scroll para manga) y se muestra en la página de serie incluso para fuentes no locales.
- `POST /api/watched` — marca capítulo visto
- `GET /api/watched/<ref>` — lista de capítulos vistos
- `POST /api/watched/toggle` — marca/desmarca
- `POST /api/delete-watched` — elimina del disco capítulos vistos (excepto el último). Salta capítulos en descarga activa (devuelve lista `skipped`) gracias al lock de `download_worker.py`
- `POST /api/delete-chapter` — elimina un capítulo individual, retrocede progreso si era el último. Rechaza con 409 si el capítulo está siendo descargado
- `GET /api/library/updates` — series con capítulos nuevos pendientes
- `POST /api/library/acknowledge-updates` — limpia flag de novedades

---

#### `api/downloads.py` — Cola de descarga

- `GET /api/queue/status` — jobs activos y pendientes
- `POST /api/download` — encola serie completa (soporta `exclude_watched`)
- `POST /api/download/chapter` — encola un capítulo individual
- `POST /api/download/chapters` — encola múltiples capítulos en batch

**Backpressure:** la cola tiene `maxsize=50`. Si está llena, los endpoints responden `503 Service Unavailable`.

---

#### `api/updates.py` — Comprobación de actualizaciones

- `POST /api/library/check-updates/<ref>` — comprueba capítulos nuevos para una serie
- `POST /api/library/check-all-updates` — comprueba todas las series en paralelo (max 4 workers)
- `_check_series_for_new_chapters(ref)` — lógica central: obtiene capítulos remotos después del máximo capítulo local (optimización: no descarga toda la lista remota si ya tienes hasta el capítulo 50, solo pide los posteriores)
- `_check_all_updates_core()` — wrapper sin dependencia Flask, reutilizado por el scheduler en `app.py`

---

#### `api/settings.py` — Configuración de fuentes

Endpoints CRUD para activar/desactivar fuentes desde el frontend:

- `GET /api/settings/sources` — devuelve todas las fuentes con su estado (activo/inactivo)
- `POST /api/settings/sources/<name>` — activa/desactiva una fuente por nombre

Usado por el popup de configuración (icono engranaje en `index.html`).

---

#### `api/scraper_configs.py` — CRUD de scrapers dinámicos

Endpoints para gestionar scrapers definidos por el usuario:

- `GET /api/scraper-configs` — lista todas las configuraciones guardadas
- `POST /api/scraper-configs` — crea/actualiza una configuración
- `DELETE /api/scraper-configs/<name>` — elimina una configuración
- `POST /api/scraper-configs/test` — prueba una configuración contra una URL real (soporta stages `search`, `details`, `chapters`, `content`; para `content` el límite de previsualización de imágenes se eliminó, mostrando todas las encontradas)
- `POST /api/scraper-configs/auto-detect` — infiere selectores automáticamente desde una URL usando `selector_detector.py`
- `POST /api/scraper-configs/detect-selectors` — detecta selectores CSS buscando elementos que contengan un texto visible específico (útil para sitios con selectores genéricos). Usa `detect_selector_by_text()` de `selector_detector.py`. Soporta stages `search`, `details`, `chapters`, `content`.
- `POST /api/scraper-configs/reload` — recarga todas las fuentes dinámicas sin reiniciar el servidor

El auto-detect funciona en 3 etapas (`search`, `details`, `chapters`) y devuelve selectores CSS candidatos que el usuario puede ajustar.

---



### `core/database.py` — SQLite

Conexión por hilo (`threading.local()`) con WAL mode.

**Migraciones versionadas** (versión actual: 9):
- Tablas: `content`, `user_progress`, `download_queue`, `watched_chapters`, `series_status`, `schema_version`, `source_settings`
- Migración #7: cambia `watched_chapters.chapter_number` de INTEGER a TEXT para soportar capítulos decimales (ej. 5.5)
- Migración #8: elimina tablas/columnas huérfanas tras migración #7
- Migración #9: índices `idx_queue_content_ref_status`, `idx_queue_status_created`, `idx_series_status_check`, `idx_series_status_updates` para eliminar full scans

**Operaciones:**
- `init_db()` — crea esquema y aplica migraciones
- `cleanup_download_queue()` — al arrancar, limpia descargas interrumpidas
- `save_content_to_db()` / `get_content_ref()` — CRUD de contenidos
- `get_progress()` / `save_progress()` — progreso usuario
- `update_queue_status()` — estado de cola de descarga
- `set_series_status()` / `get_series_status()` — etiquetas biblioteca
- `mark_chapter_as_watched()` / `is_chapter_watched()` — capítulos vistos
- `get_series_to_check()` / `mark_series_checked()` — para scheduler de actualizaciones
- `set_series_updates()` / `get_series_with_updates()` — capítulos nuevos detectados
- `get_source_settings()` / `update_source_setting()` — configuración de fuentes (activo/inactivo)
- `get_enabled_sources()` — filtra solo fuentes habilitadas

---

### `core/disk_cache.py` — Caché en disco

Clase `DiskCache` con:

- Clave hasheada con MD5 + namespace (evita colisiones)
- TTL por entrada (default 24 h)
- Escritura atómica (temp → rename)
- `get(key)` → devuelve valor o `None` si expirado
- `set(key, value, ttl?)` → guarda con expiración
- `aget(key)` / `aset(key, value, ttl?)` → versiones async que usan `asyncio.to_thread()`
  para no bloquear el event loop (usadas por los endpoints async de búsqueda)
- `evict_expired()` → elimina entradas vencidas
- `delete(key)` / `clear()` → limpieza manual

Instancia global `search_cache` usada por todas las fuentes para cachear catálogos, detalles y capítulos.

---

### `core/download_worker.py` — Workers de descarga

Arquitectura productor-consumidor con `Queue(maxsize=50)`:

- `download_queue`: cola threadsafe de jobs (con backpressure, `maxsize=50`)
- `_active_jobs`: dict con lock para jobs en curso
- `_stop_event`: `threading.Event` que permite el graceful shutdown de los workers
- `start_workers(n)`: inicia N hilos daemon (default `DOWNLOAD_NUM_WORKERS` desde config)
- `stop_workers()`: señaliza a los workers que deben terminar

Cada worker:
1. Toma un job de la cola (con timeout de 1 s para poder detectar `_stop_event`)
2. Resuelve capítulos a descargar (`_resolve_chapters` — UNA llamada HTTP)
3. Crea carpeta de destino (`normalize_title`)
4. Descarga portada, genera thumbnail WebP (`thumb.webp` a 200px via ffmpeg) y guarda `series_info.json` (`_save_series_metadata`)
5. Itera capítulos llamando a `source.download_chapter_sync()` (los workers se ejecutan en hilos, por lo que usan los métodos `_sync` directamente en vez de los wrappers async)
6. Actualiza progreso en BD con frecuencia regulada (flush cada 30 s, en vez de cada N capítulos)
7. Marca completado e invalida el índice de series

**Nota:** el worker usa siempre los métodos `_sync` (`get_details_sync`, `get_chapters_sync`, `download_chapter_sync`) para evitar el overhead de `asyncio.to_thread()` dentro de un hilo que ya es síncrono.

**Fix aplicado:** se eliminó el `try/except` que importaba `DOWNLOAD_NUM_WORKERS` con fallback a 3,
ya que `config.py` ahora exporta correctamente la variable desde `core/settings.py`.

**Lock de descargas activas:** `_downloading_chapters: dict[str, set[str]]` mapea serie → conjunto de capítulos
en descarga. Funciones thread-safe `mark_downloading(series_folder, chapter)`, `unmark_downloading(...)`,
`is_downloading(...)` previenen que `api_delete_watched` y `api_delete_chapter` eliminen archivos
mientras el worker los está escribiendo. El lock es en memoria y se pierde al reiniciar.

---

### `core/http_pool.py` — Pool HTTP compartido

Gestiona sesiones HTTP usando `threading.local()` para dar a cada hilo su propia
`requests.Session()` y `cloudscraper.CloudScraper`:

- `HttpPool.get_session()` → `requests.Session` thread-local con `pool_connections=20`, `pool_maxsize=40`
- `HttpPool.get_scraper()` → `cloudscraper.CloudScraper` thread-local montado sobre el mismo pool

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
directorio (excluyendo `__init__.py`) y reúne instancias en un diccionario.

```python
# Estructura resultante (auto-descubierta — varía según fuentes cargadas):
SOURCES = {
    'anime': {'jkanime': JkanimeSource(), 'animeflv': AnimeflvSource()},
    'manga': {'nartag': NartagSource(), 'manhwaweb': ManhwawebSource(), 'ikigai': IkigaiSource(), 'olympus': OlympusSource()}
}
# Además se cargan scrapers dinámicos desde core/scraper_config.py bajo SOURCES['dynamic']
```

Funciones:
- `discover_sources()` → escanea y registra fuentes (se llama al importar)
- `get_source(type, name)` → devuelve instancia o `None`
- `get_source_list()` → devuelve `list[dict]` con `{type, name, label}` para el frontend
- `get_enabled_source_list()` → igual pero filtrado por `get_enabled_sources()` en BD

---

### `core/throttle.py` — Rate limiter

Per-domain rate limiter con algoritmo **token bucket**. Espera un mínimo de 2 segundos entre requests al mismo dominio.

- `wait(url)` — versión sync con `threading.Event.wait()` (sin busy-wait) y `threading.Lock`
- `async_wait(url)` — versión async con el mismo `threading.Lock` (anteriormente usaba un `asyncio.Lock` separado, lo que causaba una race condition: el estado compartido `_last_calls` podía ser modificado concurrentemente por ambas rutas)
- `_get_remaining(domain)` — devuelve segundos restantes hasta la próxima llamada permitida

Usa `urlparse` para extraer el netloc. Instancia global `rate_limiter` con `min_interval=2.0`.

---

### `core/scraper_config.py` — Scrapers dinámicos

Gestiona scrapers definidos por el usuario (sin código) a través de configuración JSON:

- **Carga**: `load_dynamic_sources()` se invoca en `core/sources.py` tras el auto-descubrimiento. Lee la tabla `scraper_configs` de la BD, genera dinámicamente clases Python que heredan de `DynamicSource` (definido en `sources/dynamic.py`) y las registra en `SOURCES['dynamic']`.
- **Validación**: `validate_config(config)` checkea que la configuración tenga estructura válida (selectores, URL, tipo de contenido).
- **Persistencia**: `save_config(name, config)` guarda en BD; `get_config(name)`, `list_configs()`, `delete_config(name)`.
- **Test**: `test_config(config, url)` ejecuta el scraper dinámico contra una URL real para verificar que los selectores funcionan.

Los usuarios definen scrapers desde el frontend mediante el endpoint `POST /api/scraper-configs/auto-detect` que infiere selectores automáticamente.

---

### `core/selector_detector.py` — Inferencia de selectores

Analiza HTML de sitios upstream para sugerir selectores CSS automáticamente:

- **`detect_search_selectors(html, url)`**: dado el HTML de una página de búsqueda/results, encuentra elementos que contienen enlaces, imágenes y títulos. Devuelve selectores candidatos para `card`, `title`, `link`, `image`, etc.
- **`detect_detail_selectors(html, url)`**: analiza página de detalle de serie para inferir selectores de portada, sinopsis, géneros.
- **`detect_chapter_selectors(html, url)`**: analiza página de capítulos para inferir selectores de ítem, número y enlace.
- **`detect_selector_by_text(html, text, stage, base_url)`**: dado un texto visible que el usuario sabe que existe en la página, busca elementos que lo contengan y sugiere selectores para la etapa indicada (`search`, `details`, `chapters`, `content`). Para el stage `content` detecta imágenes lazy-loading: si un `<img>` tiene `src=""` y `data-src` poblado (o clases `page-img-lazy`, `lazy`, `lozad`), sugiere `data-src` como atributo en vez de `src`.
- **`_find_elements_by_text(soup, text)`**: helper que busca nodos de texto que contengan el texto exacto, rankeando por puntuación de coincidencia exacta.
- **`_find_parent_card(element, card_tags)`**: helper que asciende en el DOM hasta encontrar un contenedor que coincida con los tags de card típicos.

Usa heurísticas como: elementos `<a>` con href, imágenes con `src` o `data-setsrc`, patrones de clase comunes, búsqueda por texto visible. Es usado por `POST /api/scraper-configs/auto-detect` y `POST /api/scraper-configs/detect-selectors` para guiar al usuario en la creación de scrapers dinámicos.

---

### `core/utils.py` — Utilidades

- `normalize_title(raw)` — limpia títulos para nombres de carpeta (ASCII, sin acentos, sin caracteres especiales, max 100 chars)
- `_normalize_path_name(text)` — normalización para comparación de rutas
- `normalize_for_comparison(text)` — solo alfanuméricos, minúsculas, sin tildes
- `scan_downloaded_series()` — escanea `ANIME_DOWNLOAD_DIR` y `MANGA_DOWNLOAD_DIR` y devuelve lista de series enriquecida con progreso desde BD. Usa `ThreadPoolExecutor(8)` para paralelizar la lectura de `series_info.json` y una sola query SQL (LEFT JOIN) en vez de N+1 contra BD. La caché del resultado dura 60s en vez de 15s.

---

### `sources/__init__.py` — BaseSource

Clase abstracta que define el contrato de todas las fuentes usando modelos Pydantic (`core/models.py`).

Cada subclase debe definir atributos de clase `type` (categoría: `"anime"`|`"manga"`)
y `label` (nombre para mostrar en UI). Estos son usados por `discover_sources()` para
el registro automático y por el frontend para el menú desplegable de fuentes.

Cada método tiene una versión **sync** (`*_sync`) y una **async** (el mismo nombre sin sufijo). Por defecto, la versión async delega a la sync mediante `loop.run_in_executor()` con un `ThreadPoolExecutor(max_workers=4)` acotado por instancia de fuente. Anteriormente usaba `asyncio.to_thread()` que crea un hilo por llamada sin límite, pudiendo saturar el sistema bajo carga.

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

### `sources/jkanime.py` — JKanime (anime)

Scraper de `jkanime.net`:

- **Búsqueda**: scraping HTML con BeautifulSoup
- **Detalles**: scraping de página de serie (portada, sinopsis)
- **Capítulos**: extrae lista de `div.numChapter` con IDs codificados en base64
- **Streaming**: decodifica base64 para obtener URL embed, usa `yt-dlp` para extraer URL directa. Propiedad `supports_streaming = True`.
- **Descarga**: `yt-dlp` con prioridad de servidores (`_SERVER_PRIORITY`). Soporta: Mediafire, Mp4upload, Mega, Streamwish, VOE, Vidhide, etc.
- **Cache**: catálogo no, solo detalles y capítulos por serie

---

### `sources/nartag.py` — Nartag (manga)

Scraper de `nartag.com`:

- **Autenticación**: POST con `form` redirect (`rk_madara_redirect`) para bypass anti-bot
- **Búsqueda**: catálogo paginado desde API interna + scraping como fallback
- **Detalles**: API + scraping
- **Capítulos**: API (`/wp-json/...`) con paginación
- **Streaming**: `get_chapter_images_sync()` reusa `_get_reader_url()` y `_extract_manga_images()` para obtener URLs de imágenes sin descargar
- **Descarga imágenes**: usa `get_chapter_images_sync()` y luego descarga, con soporte de `<noscript>` para lazy-loading
- **Cache**: catálogo completo (TTL 3 días), detalles y capítulos por serie

---

### `sources/manhwaweb.py` — ManhwaWeb (manga)

Scraper de `manhwaweb.com`:

- **Búsqueda**: catálogo desde API backend (`manhwawebbackend-production.up.railway.app`) con paginación paralela (8 workers por lote, max 500 páginas). Fallback a scraping HTML.
- **Detalles**: API + scraping
- **Capítulos**: API (campo `chapters[]`) + scraping de enlaces `/leer/`
- **Streaming**: `get_chapter_images_sync()` obtiene URLs de imágenes vía API o scraping, sin descargar
- **Descarga imágenes**: usa `get_chapter_images_sync()` y luego descarga por lotes con retry (3 intentos, backoff exponencial)
- **Cache**: catálogo completo (TTL 3 días), detalles y capítulos por serie
- **Background**: `warm_cache()` + `_refresh_catalog_background()` en daemon threads

---

### `sources/ikigai.py` — VisorIkigai (manga)

Scraper de `ikigai.yomod.xyz`:

- **Búsqueda**: catálogo desde API con paginación secuencial
- **Detalles y capítulos**: API REST
- **Streaming**: `get_chapter_images_sync()` extrae URLs de imágenes vía scraping de la página del capítulo
- **Descarga imágenes**: usa `get_chapter_images_sync()` y luego descarga secuencial
- **Cache**: catálogo completo, detalles y capítulos
- Usa `cloudscraper` para bypass de Cloudflare

---

### `sources/dynamic.py` — Motor de scrapers dinámicos

Clase `DynamicSource` que hereda de `BaseSource` y ejecuta scrapers definidos por configuración JSON (sin código):

- **Configuración**: recibe un dict con `search_selector`, `detail_selectors`, `chapter_selectors`, `content_type`, etc.
- **Búsqueda**: usa `soup.select(config['search_selector'])` para extraer resultados. También inspecciona `<template>` tags para sitios con patrón "load more" (deduplica por `href`).
- **Catálogo**: si `has_catalog = true`, `search_sync()` construye el catálogo completo desde `catalog_url_template` (paginado con `{page}`, stop cuando una página devuelve 0 items o se alcanza `catalog_max_pages`). El catálogo se cachea con `DiskCache` (TTL configurable vía `catalog_cache_ttl`). La precarga se lanza en `warm_cache_sync()` con un lock por fuente para evitar refrescos concurrentes (cooldown de 24 h entre reconstrucciones, estilo ikigai). La búsqueda por query filtra localmente sobre el catálogo cacheado.
- **Detalles**: extrae portada, sinopsis y géneros según selectores configurados.
- **Capítulos**: extrae lista numerada de capítulos desde selectores CSS.
- **Streaming/descarga**: según `content_type` (`image` o `video`):
  - `image`: extrae URLs de imágenes con `content_image_selector` + `content_image_attr`. El atributo por defecto es `src`, pero puede configurarse a `data-src` para sitios con lazy loading.
  - `video`: extrae una URL de video con `content_video_selector` + `content_video_attr`.
- **Propiedad `supports_streaming`**: retorna `True` solo si `content_type == 'video'`, usado por el frontend para mostrar el botón de reproducción.
- **Cache**: usa `search_cache` con TTL por defecto.

Las instancias son creadas por `core/scraper_config.py` y registradas automáticamente en `SOURCES['dynamic']`.

---



## Frontend

### Templates Jinja2

Herencia: `base.html` → `{index, serie, reader}.html`

El proyecto usa **build en dos modos**:

- **Producción** (`python3 scripts/build.py`): genera bundles minificados con content hash en `static/dist/`. `routers/pages.py` carga el manifiesto (`build.json`) y lo pasa al contexto Jinja2 como `{{ bundles }}`. Cada template carga un único CSS + JS por página.
- **Desarrollo** (sin build): los templates cargan los archivos individuales como fallback, permitiendo editar CSS/JS sin recompilar.

- **`base.html`**: layout raíz. En producción carga preload hints para Inter y FA subset. En desarrollo carga `inter.css`, `fa-subset.css`, `base.css`, `layout.css`, `toast.js`, `confirm.js` y `queue-indicator.js`. Siempre incluye helpers inline de modal y animación de cards.
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
- **`inter.css`**: define `@font-face` para Inter en woff2 (pesos 400, 500, 600, 700, 800). El peso 300 fue eliminado por no usarse.
- **`fa-subset.css`**: subset de Font Awesome Free con solo los 28 iconos realmente usados. Incluye `@font-face` apuntando a `fa-solid-900-subset.woff2`. Se usa tanto en desarrollo como en producción.

### JavaScript

- **`app.js`**: tabs (Anime/Manga), búsqueda, biblioteca con filtros por estado, notificaciones toast, popup de estado, configuración de fuentes (icono engranaje → popup con checkboxes para activar/desactivar fuentes)
- **`serie.js`**: carga de capítulos, descarga individual/completa, marcado como visto (watched), detección de actualizaciones. Progreso visible tanto para contenido local como remoto (ya no se oculta la sección de progreso para `source !== 'local'`). Botón "Continuar" navega a la URL correcta según la fuente, y se muestra también para series remotas (no solo locales). Determina si mostrar botón "Reproducir en streaming" mediante `window.serieData.canStream` (enviado desde `routers/pages.py`), eliminando la whitelist hardcodeada `STREAMABLE_SOURCES`. Usa `classList.remove('hidden')` en vez de `style.display` para mostrar/ocultar botones (CSS define `.hidden` con `!important`).
- **`reader.js`**: reproductor de video con guardado de progreso cada 5s, visor de manga con scroll virtual, atajos de teclado, precarga proactiva de imágenes (`_prefetchNextBatch`) — carga hasta 3 imágenes más allá de la ventana actual con `new Image()` y delay progresivo de 200ms. Guarda progreso en BD tanto para contenido local como remoto mediante `POST /api/progress/{type}/{source}/{content_id}`.
- **`settings.js`**: wizard de 6 pasos para crear/editar scrapers dinámicos. Incluye: campos de texto de muestra + botón "Detectar" por cada paso (usa `detectByText()` que llama a `/api/scraper-configs/detect-selectors`), toggle de catálogo con campos específicos, `getCatalogConfig()`, `toggleCatalogSection()`. Maneja la creación, edición y guardado de configuraciones.
- **`queue-indicator.js`**: indicador flotante de descargas activas con popup de progreso. Usa `fa-arrow-down` en vez de `fa-arrow-down-to-line` (no existente en FA6).

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
2. **Agrupa por página**: para cada template (`index`, `serie`, `reader`) concatena su CSS específico con el CSS común (`base.css`, `layout.css`). Lo mismo con JS (cada página obtiene solo el JS que necesita, sin `queue-indicator.js` que va en base).
3. **Minifica**: usa `cssmin` para CSS y `jsmin` para JS.
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
- El CSS original `fontawesome.min.css` y las fuentes `Inter-300` se eliminaron por no usarse. Solo se usa `fa-subset.css` en todos los entornos.
- Se corrigió `queue-indicator.js` para usar `fa-arrow-down` (`f063`) en vez de `fa-arrow-down-to-line` (inexistente en FA6 Free, causaba icono fantasma).

### Inter — conversión TTF → woff2 (65% de reducción)

- Los 6 pesos TTF originales (~1.49 MB total) se convirtieron a woff2 (~523 KB total) usando `google/woff2`.
- El peso 300 fue eliminado por no estar referenciado en ningún `font-family` ni template.
- `inter.css` actualizado para servir woff2 con formato `woff2` y fallback a `woff`.

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

- Cada página recibe exactamente un CSS bundle y un JS bundle (sin duplicación de CSS común).
- Se eliminaron dependencias de librerías externas (Font Awesome inline, etc.) que ya no se necesitaban en producción.
- `build.py` no requiere Node.js ni npm — corre con Python estándar + `cssmin` y `jsmin` (instalables vía pip).
