# AnyOne — Arquitectura

Aplicación web Flask para buscar, descargar y leer/ver anime y manga desde múltiples fuentes (scrapers).

---

## Estructura general

```
AnyOne/
├── app.py                    → Factory de la app Flask
├── config.py                 → Variables de entorno y rutas
├── requirements.txt          → Dependencias Python
├── Dockerfile                → Imagen Docker (python:3.12-slim)
├── docker-compose.yml        → Orquestación local
│
├── blueprints/               → Flask blueprints (rutas)
│   ├── main.py               →   Rutas HTML (/, /serie, /reader)
│   └── api/                  →   API REST empaquetada (/api/*)
│       ├── __init__.py       →   Crea el blueprint y exporta _check_all_updates_core
│       ├── common.py         →   Helpers compartidos (índice en memoria, cola, fs)
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
└── static/                   → Frontend
    ├── css/
    │   ├── base.css          →   Design tokens, componentes (cards, modal, spinner…)
    │   ├── layout.css        →   Nav, page-content, responsive breakpoints
    │   ├── index.css         →   Filtros de biblioteca
    │   ├── serie.css         →   Cover parallax, hero, synopsis
    │   └── reader.css        →   Lector full-screen, controles
    └── js/
        ├── app.js            →   Lógica de index.html
        ├── serie.js          →   Lógica de serie.html
        ├── reader.js         →   Lógica de reader.html
        └── queue-indicator.js →  Indicador flotante de descargas
```

---

## Módulos — descripción y funcionamiento

### `config.py` — Configuración (legacy bridge)

Wrapper delgado que re-exporta las variables de `core/settings.py` para compatibilidad
con imports existentes (`from config import ANIME_DOWNLOAD_DIR`).

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

### `app.py` — Application factory

Punto de entrada. `create_app()`:

1. Crea la app Flask, carga `config.py`, activa CORS
2. Registra el handler global de `ValidationError` (Pydantic) → 400 JSON
3. Ejecuta migraciones de BD (`init_db`)
4. Limpia la cola de descargas interrumpidas (`cleanup_download_queue`)
5. Inicia 3 workers de descarga en hilos daemon
6. Arranca el scheduler de actualizaciones (cada 24 h)
7. Registra los blueprints (`main`, `api`)
8. Lanza precarga en background de todas las fuentes (`warm_cache`)

---

### `blueprints/main.py` — Rutas HTML

Tres rutas que renderizan templates Jinja2:

| Ruta | Template | Función |
|------|----------|---------|
| `/` | `index.html` | Página principal (búsqueda + biblioteca local) |
| `/serie/<type>/<source>/<id>` | `serie.html` | Detalle de serie y lista de capítulos |
| `/reader/<type>/<source>/<content_id>/<chapter>` | `reader.html` | Lector/reproductor a pantalla completa |

Sin lógica propia — todo el peso está en el frontend (JS) y la API.

---

### `blueprints/api/` — API REST (paquete)

Antes un solo archivo de ~1180 líneas, ahora modularizado en 6 submódulos. Corazón del backend.

---

#### `api/common.py` — Helpers compartidos

Funciones y estado global reutilizados por todos los submódulos:

- `_safe_path(base, untrusted)` — previene path traversal
- `_build_series_index` / `_get_series_index` / `_invalidate_series_index` — índice en memoria de series locales (content_id → Path)
- `_find_local_serie_dir` — busca carpeta por content_id (índice O(1) + fallback por normalización)
- `_local_chapters_anime` / `_local_chapters_manga` — lista capítulos locales
- `_delete_chapter_files` — elimina archivos de un capítulo en disco
- `_resolve_series_title` — resuelve título desde BD o disco
- `_queue_find_active` / `_queue_insert` / `_queue_get_status` — acceso a la cola de descarga
- `_base_folder` / `_get_json` / `_require_local` / `_content_title_by_ref` — utilidades menores
- `_parse_json_body(model_class)` — parsea el body JSON con un modelo Pydantic, lanza `ValidationError` si los datos no son válidos

---

#### `api/search.py` — Búsqueda

- `GET /api/search?type=...&source=...&q=...` — busca en una fuente (con caché + progreso enriquecido)
- `GET /api/search-all?type=...&q=...` — busca en todas las fuentes del tipo (ThreadPoolExecutor + dedup)
- `GET /api/search-all-stream?type=...&q=...` — SSE con resultados progresivos (timeout 90s, cachea para visitas posteriores)

---

#### `api/content.py` — Contenido y reproducción

- `GET /api/content/<type>/<source>/<id>` — portada, sinopsis
- `GET /api/chapters/<type>/<source>/<id>` — lista remota de capítulos
- `GET /api/chapters/with-local/<type>/<source>/<id>` — remotos marcando descargados
- `GET /api/content/local/<type>/<id>` — detalle de contenido local
- `GET /api/chapters/local/<type>/<id>` — capítulos locales en disco
- `GET /api/local-cover/<type>/<path:filename>` — sirve portada local
- `GET /api/play/<type>/<source>/<id>/<chapter>` — sirve video local
- `GET /api/play/local/<type>/<id>/<chapter>` — reproducción local (path traversal safe)
- `GET /api/manga/images/<path:subpath>` — imágenes de manga
- `GET /api/video-duration/anime/<id>/<chapter>` — duración del video con ffprobe

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

---

#### `api/updates.py` — Comprobación de actualizaciones

- `POST /api/library/check-updates/<ref>` — comprueba capítulos nuevos para una serie
- `POST /api/library/check-all-updates` — comprueba todas las series en paralelo (max 4 workers)
- `_check_series_for_new_chapters(ref)` — lógica central: compara capítulos remotos vs locales
- `_check_all_updates_core()` — wrapper sin dependencia Flask, reutilizado por el scheduler en `app.py`

---

### `core/database.py` — SQLite

Conexión por hilo (`threading.local()`) con WAL mode.

**Migraciones versionadas** (versión actual: 5):
- Tablas: `content`, `user_progress`, `download_queue`, `watched_chapters`, `series_status`, `schema_version`

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

---

### `core/disk_cache.py` — Caché en disco

Clase `DiskCache` con:

- Clave hasheada con MD5 + namespace (evita colisiones)
- TTL por entrada (default 24 h)
- Escritura atómica (temp → rename)
- `get(key)` → devuelve valor o `None` si expirado
- `set(key, value, ttl?)` → guarda con expiración
- `evict_expired()` → elimina entradas vencidas
- `delete(key)` / `clear()` → limpieza manual

Instancia global `search_cache` usada por todas las fuentes para cachear catálogos, detalles y capítulos.

---

### `core/download_worker.py` — Workers de descarga

Arquitectura productor-consumidor con `Queue`:

- `download_queue`: cola threadsafe de jobs
- `_active_jobs`: dict con lock para jobs en curso
- `start_workers(n)`: inicia N hilos daemon (default 3)

Cada worker:
1. Toma un job de la cola
2. Resuelve capítulos a descargar (`_resolve_chapters` — UNA llamada HTTP)
3. Crea carpeta de destino (`normalize_title`)
4. Descarga portada y guarda `series_info.json` (`_save_series_metadata`)
5. Itera capítulos llamando a `source.download_chapter()`
6. Actualiza progreso cada 5 capítulos
7. Marca completado e invalida el índice de series

---

### `core/sources.py` — Registro de fuentes

```python
SOURCES = {
    'anime': {'jkanime': JkanimeSource()},
    'manga': {'nartag': NartagSource(), 'manhwaweb': ManhwawebSource(), 'ikigai': IkigaiSource()}
}
```

Función `get_source(type, name)` → instancia o `None`.

---

### `core/throttle.py` — Rate limiter

Per-domain rate limiter con lock. Espera un mínimo de 2 segundos entre requests al mismo dominio. Usa `urlparse` para extraer el netloc.

---

### `core/utils.py` — Utilidades

- `normalize_title(raw)` — limpia títulos para nombres de carpeta (ASCII, sin acentos, sin caracteres especiales, max 100 chars)
- `_normalize_path_name(text)` — normalización para comparación de rutas
- `normalize_for_comparison(text)` — solo alfanuméricos, minúsculas, sin tildes
- `scan_downloaded_series()` — escanea `ANIME_DOWNLOAD_DIR` y `MANGA_DOWNLOAD_DIR` y devuelve lista de series enriquecida con progreso desde BD

---

### `sources/__init__.py` — BaseSource

Clase abstracta que define el contrato de todas las fuentes usando modelos Pydantic (`core/models.py`):

| Método | Retorno | Descripción |
|--------|---------|-------------|
| `search(query)` | `list[SearchResult]` | Busca por título |
| `get_details(id)` | `SeriesDetails` | Portada, sinopsis, tipo, género |
| `get_chapters(id)` | `list[Chapter]` | Capítulos con `{number, id}` |
| `download_chapter(id, chapter_id, dest)` | `str` | Descarga un capítulo, devuelve ruta |
| `get_stream_url(id, chapter_id)` | `str\|None` | URL directa para streaming (solo anime) |
| `warm_cache()` | `None` | Precarga catálogo en background (opcional) |

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

- **`base.html`**: layout raíz. Carga Google Fonts (Inter), Font Awesome, `base.css`, `layout.css`, JS global (`queue-indicator.js`), helpers de modal y animación de cards
- **`index.html`**: dos paneles (Anime / Manga) con pestañas, búsqueda por fuente, biblioteca local con filtros por estado
- **`serie.html`**: portada con parallax, sinopsis expandible, lista de capítulos con botones de play/download/watched, badge de actualizaciones
- **`reader.html`**: reproductor de video o visor de manga a pantalla completa

### CSS — Design system

- **`base.css`**: tokens (`:root`), reset, componentes reutilizables (buttons, cards, modal, spinner, progress bar, scrollbar, animaciones)
- **`layout.css`**: navegación sticky con blur, estructura de página, responsive breakpoints
- **`index.css`**: filtros de biblioteca tipo chip con scroll horizontal en móvil
- **`serie.css`**: efecto parallax en cover, hero card, expansión de sinopsis
- **`reader.css`**: layout full-screen, barra de controles, botones de navegación

### JavaScript

- **`app.js`**: tabs (Anime/Manga), búsqueda, biblioteca con filtros por estado, notificaciones toast, popup de estado
- **`serie.js`**: carga de capítulos, progreso, descarga individual/completa, marcado como visto, detección de actualizaciones
- **`reader.js`**: reproductor de video con guardado de progreso cada 5s, visor de manga con scroll virtual, atajos de teclado
- **`queue-indicator.js`**: indicador flotante de descargas activas con popup de progreso

---

## Flujo de datos típico

### Búsqueda
```
Usuario escribe "naruto" → JS llama GET /api/search/anime/jkanime?q=naruto
  → api/search.py llama source.search(query)
    → scraper hace HTTP a jkanime.net, parsea HTML
  → api/search.py enriquece resultados con estado de BD (descargado, progreso)
→ JS renderiza grid de resultados
```

### Descarga
```
Usuario hace clic en "Descargar serie completa"
  → JS POST /api/download {type, source, content_id, title}
    → api/downloads.py encola job en download_queue (SQLite)
  → Worker toma el job:
      1. get_chapters() → lista remota
      2. Crea carpeta: /Descargas/Manga/naruto/
      3. Descarga portada + series_info.json
      4. Por cada capítulo: download_chapter() → imágenes
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
