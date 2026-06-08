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
│       └── updates.py        →   Comprobación de capítulos nuevos
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
│   └── utils.py              →   Normalización de títulos, escaneo local
│
├── sources/                  → Scrapers (uno por sitio upstream)
│   ├── __init__.py           →   Clase base BaseSource
│   ├── animeflv.py           →   www3.animeflv.net (anime)
│   ├── jkanime.py            →   jkanime.net (anime)
│   ├── nartag.py             →   nartag.com (manga)
│   ├── manhwaweb.py          →   manhwaweb.com (manga)
│   ├── ikigai.py             →   visorikigai (manga)
│   └── olympus.py            →   olympusscanlation (manga)
│
├── templates/                → Jinja2 (server-side rendered)
│   ├── base.html             →   Layout: fonts, icons, CSS, JS globales
│   ├── index.html            →   Home: búsqueda + biblioteca
│   ├── serie.html            →   Detalle de serie (capítulos, portada)
│   └── reader.html           →   Lector de video / manga
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
    │   ├── inter.css         →   Face-font de Inter (local, woff2)
    │   ├── fontawesome.min.css → Iconos Font Awesome (local, sin CDN, ya no se usa en prod)
    │   └── fa-subset.css     →   Subset de FA solo con los 28 iconos usados
    ├── fonts/
    │   ├── Inter-{300,400,500,600,700,800}.ttf   → Pesos de Inter (TTF, solo dev)
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
        └── reader.{hash}.js  →   JS empaquetado para reader.html
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

**Modelos internos:**
- `DownloadJob` — job tipado para la cola de descarga

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
7. Monta `StaticFiles` y registra los routers (`pages`, `api`)
8. Lanza precarga en background de todas las fuentes (`asyncio.create_task(_warm_all_sources())`)
9. Al shutdown: detiene los workers gracefulmente (`stop_workers()`)

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

Sin lógica propia — todo el peso está en el frontend (JS) y la API.

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
- `GET /api/play/<type>/<source>/<id>/<chapter>` — sirve video local
- `GET /api/play/local/<type>/<id>/<chapter>` — reproducción local (path traversal safe)
- `GET /api/manga/images/<path:subpath>` — imágenes de manga (con `Cache-Control: max-age=86400` y `ETag` para 304 Not Modified)
- `GET /api/video-duration/anime/<id>/<chapter>` — duración del video con ffprobe (cached 24 h)

---

#### `api/library.py` — Biblioteca, progreso, etiquetas, vistos

- `GET /api/library` — lista de series descargadas
- `GET/POST /api/library/status` y `GET /api/library/status/<ref>` — etiquetas (watching/completed/pending/none)
- `GET/POST /api/progress/<type>/<source>/<id>` y `/progress/local/<type>/<id>` — progreso de usuario
- `POST /api/watched` — marca capítulo visto
- `GET /api/watched/<ref>` — lista de capítulos vistos
- `POST /api/watched/toggle` — marca/desmarca
- `POST /api/delete-watched` — elimina del disco capítulos vistos (excepto el último)
- `POST /api/delete-chapter` — elimina un capítulo individual, retrocede progreso si era el último
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
- `_check_series_for_new_chapters(ref)` — lógica central: compara capítulos remotos vs locales
- `_check_all_updates_core()` — wrapper sin dependencia Flask, reutilizado por el scheduler en `app.py`

---

#### `api/settings.py` — Configuración de fuentes

Endpoints CRUD para activar/desactivar fuentes desde el frontend:

- `GET /api/settings/sources` — devuelve todas las fuentes con su estado (activo/inactivo)
- `POST /api/settings/sources/<name>` — activa/desactiva una fuente por nombre

Usado por el popup de configuración (icono engranaje en `index.html`).

---

### `core/database.py` — SQLite

Conexión por hilo (`threading.local()`) con WAL mode.

**Migraciones versionadas** (versión actual: 6):
- Tablas: `content`, `user_progress`, `download_queue`, `watched_chapters`, `series_status`, `schema_version`, `source_settings`

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
# Estructura resultante (generada automáticamente):
SOURCES = {
    'anime': {'jkanime': JkanimeSource()},
    'manga': {'nartag': NartagSource(), 'manhwaweb': ManhwawebSource(), 'ikigai': IkigaiSource()}
}
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
| `warm_cache_sync()` | `warm_cache()` | `None` | Precarga catálogo en background (opcional) |

**Uso:**
- La API FastAPI (async) llama a los métodos async (`await source.search(...)`)
- Los download workers (hilos) llaman a los métodos sync (`source.search_sync(...)`)

---

### `sources/jkanime.py` — JKanime (anime)

Scraper de `jkanime.net`:

- **Búsqueda**: scraping HTML con BeautifulSoup
- **Detalles**: scraping de página de serie (portada, sinopsis)
- **Capítulos**: extrae lista de `div.numChapter` con IDs codificados en base64
- **Streaming**: decodifica base64 para obtener URL embed, usa `yt-dlp` para extraer URL directa
- **Descarga**: `yt-dlp` con prioridad de servidores (`_SERVER_PRIORITY`). Soporta: Mediafire, Mp4upload, Mega, Streamwish, VOE, Vidhide, etc.
- **Cache**: catálogo no, solo detalles y capítulos por serie

---

### `sources/nartag.py` — Nartag (manga)

Scraper de `nartag.com`:

- **Autenticación**: POST con `form` redirect (`rk_madara_redirect`) para bypass anti-bot
- **Búsqueda**: catálogo paginado desde API interna + scraping como fallback
- **Detalles**: API + scraping
- **Capítulos**: API (`/wp-json/...`) con paginación
- **Descarga imágenes**: iteración sobre `<img>` en página del capítulo, con soporte de `<noscript>` para lazy-loading
- **Cache**: catálogo completo (TTL 3 días), detalles y capítulos por serie

---

### `sources/manhwaweb.py` — ManhwaWeb (manga)

Scraper de `manhwaweb.com`:

- **Búsqueda**: catálogo desde API backend (`manhwawebbackend-production.up.railway.app`) con paginación paralela (8 workers por lote, max 500 páginas). Fallback a scraping HTML.
- **Detalles**: API + scraping
- **Capítulos**: API (campo `chapters[]`) + scraping de enlaces `/leer/`
- **Descarga imágenes**: API (`/chapters/see/{chapter_id}`) o scraping. Descarga por lotes con retry (3 intentos, backoff exponencial)
- **Cache**: catálogo completo (TTL 3 días), detalles y capítulos por serie
- **Background**: `warm_cache()` + `_refresh_catalog_background()` en daemon threads

---

### `sources/ikigai.py` — VisorIkigai (manga)

Scraper de `ikigai.yomod.xyz`:

- **Búsqueda**: catálogo desde API con paginación secuencial
- **Detalles y capítulos**: API REST
- **Descarga imágenes**: API → lista de URLs → descarga secuencial
- **Cache**: catálogo completo, detalles y capítulos
- Usa `cloudscraper` para bypass de Cloudflare

---

## Frontend

### Templates Jinja2

Herencia: `base.html` → `{index, serie, reader}.html`

El proyecto usa **build en dos modos**:

- **Producción** (`python3 scripts/build.py`): genera bundles minificados con content hash en `static/dist/`. `routers/pages.py` carga el manifiesto (`build.json`) y lo pasa al contexto Jinja2 como `{{ bundles }}`. Cada template carga un único CSS + JS por página.
- **Desarrollo** (sin build): los templates cargan los archivos individuales como fallback, permitiendo editar CSS/JS sin recompilar.

- **`base.html`**: layout raíz. En producción carga preload hints para Inter y FA subset. En desarrollo carga `inter.css`, `fontawesome.min.css`, `base.css`, `layout.css` y `queue-indicator.js`. Siempre incluye helpers inline de modal y animación de cards.
- **`index.html`**: dos paneles (Anime / Manga) con pestañas, búsqueda por fuente (dropdown dinámico que solo muestra fuentes habilitadas), botón de engranaje para abrir popup de configuración de fuentes, biblioteca local con filtros por estado. Carga `bundles.css_index` + `bundles.js_index` (o `index.css` + `app.js` en dev).
- **`serie.html`**: portada con parallax, sinopsis expandible, lista de capítulos con botones de play/download/watched, badge de actualizaciones. Carga `bundles.css_serie` + `bundles.js_serie`.
- **`reader.html`**: reproductor de video o visor de manga a pantalla completa. Carga `bundles.css_reader` + `bundles.js_reader`.

### CSS — Design system

- **`base.css`**: tokens (`:root`), reset, componentes reutilizables (buttons, cards, modal, spinner, progress bar, scrollbar, animaciones). Incluye clases extraídas de inline styles: `.card-dl-btn`, `.resume-btn`, `.status-tag-btn`, `.card-actions-row`, `.card-chips-nowrap`, `.chip-sm`.
- **`layout.css`**: navegación sticky con blur, estructura de página, responsive breakpoints
- **`index.css`**: filtros de biblioteca tipo chip con scroll horizontal en móvil
- **`serie.css`**: efecto parallax en cover, hero card, expansión de sinopsis, clase `.back-link`
- **`reader.css`**: layout full-screen, barra de controles, botones de navegación
- **`inter.css`**: define `@font-face` para Inter en woff2 (pesos 400, 500, 600, 700, 800). El peso 300 fue eliminado por no usarse.
- **`fa-subset.css`**: subset de Font Awesome Free con solo los 28 iconos realmente usados. Incluye `@font-face` apuntando a `fa-solid-900-subset.woff2`. La versión completa (`fontawesome.min.css`, 84KB) solo se usa en desarrollo como fallback.

### JavaScript

- **`app.js`**: tabs (Anime/Manga), búsqueda, biblioteca con filtros por estado, notificaciones toast, popup de estado, configuración de fuentes (icono engranaje → popup con checkboxes para activar/desactivar fuentes)
- **`serie.js`**: carga de capítulos, progreso, descarga individual/completa, marcado como visto, detección de actualizaciones
- **`reader.js`**: reproductor de video con guardado de progreso cada 5s, visor de manga con scroll virtual, atajos de teclado, precarga proactiva de imágenes (`_prefetchNextBatch`) — carga hasta 3 imágenes más allá de la ventana actual con `new Image()` y delay progresivo de 200ms
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
    → Por cada serie: compara capítulos remotos vs locales
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

Además, en producción se emiten **preload hints** para los font files críticos y se agregan headers de caché agresivos (`Cache-Control: public, max-age=31536000, immutable`) a través de un middleware en `server.py` para toda la carpeta `/static/dist/`.

### Cache headers

En `server.py` se configuran dos niveles de caché:

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
- El CSS original `fontawesome.min.css` (84KB) se mantiene como fallback en desarrollo.
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
