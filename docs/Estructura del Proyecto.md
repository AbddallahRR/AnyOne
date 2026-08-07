---
tags: [anyone, estructura, codigo]
tema: any
estado: activo
descripcion: Árbol de directorios y responsabilidades de cada módulo
---

# Estructura del Proyecto

```
AnyOne/
├── app.py                  # Entrada FastAPI: lifespan, middlewares, montajes, /health
├── entrypoint.py           # Arranque Docker: ajusta permisos y baja a UID/GID 1000
├── docker-compose.yml      # Orquestación Docker (puerto 5000, volúmenes)
├── Dockerfile              # Build multi-etapa (builder + imagen slim con ffmpeg)
├── pyproject.toml          # Config de ruff y mypy
├── requirements.txt        # Dependencias Python (pinadas)
│
├── core/                   # Infraestructura y lógica de negocio
│   ├── settings.py         # Configuración (pydantic-settings) → [[Configuración]]
│   ├── sources.py          # Registro, descubrimiento y habilitación de fuentes → [[Fuentes]]
│   ├── models.py           # Modelos Pydantic (dominio + API + configs de scraper)
│   ├── database.py         # Re-exporta toda la capa de BD → [[Modelo de Datos]]
│   ├── db/                 # Implementación de BD por dominio
│   │   ├── connection.py   # Conexión SQLite, migraciones, limpieza de cola
│   │   ├── content.py      # Tabla `content`
│   │   ├── downloads.py    # Tabla `download_queue`
│   │   ├── library.py      # Tabla `series_status` (estados, updates)
│   │   ├── progress.py     # Tabla `user_progress`
│   │   ├── settings.py     # Tabla `source_settings`
│   │   └── watched.py      # Tabla `watched_chapters`
│   ├── download_worker.py  # Cola y workers de descarga, post-proceso ffmpeg
│   ├── disk_cache.py       # Caché L1/L2 en disco → [[DiskCache]]
│   ├── http_pool.py        # Sesiones requests/cloudscraper por hilo
│   ├── throttle.py         # Rate limiter por dominio
│   ├── html_utils.py       # Utilidades DOM: imágenes, scripts, selectores
│   ├── chapter_utils.py    # Normalización de números de capítulo y ficheros
│   ├── utils.py            # Escaneo de series, títulos, filtrado de imágenes
│   ├── scraper_config.py   # CRUD de configs y generación de stubs de fuentes
│   ├── scraper_health.py   # Circuit breaker por fuente (3 fallos → 5 min off)
│   └── selector_detector.py# Auto-detección de selectores CSS
│
├── sources/                # Implementaciones de fuentes → [[Fuentes]]
│   ├── __init__.py         # BaseSource (contrato sync/async)
│   ├── common.py           # HttpClientMixin + MangaDownloadHelper
│   ├── jkanime.py          # Anime (jkanime.net)
│   ├── ikigai.py           # Manga (visualikigai)
│   ├── dynamic.py          # Motor de scrapers configurables
│   ├── manhwaweb.py        # Deshabilitada (# --- IGNORE ---)
│   └── nartag.py           # Deshabilitada (# --- IGNORE ---)
│
├── routers/
│   ├── pages.py            # Rutas HTML (/, /settings, /serie/..., /reader/...)
│   └── api/                # API REST bajo /api → [[API]]
│       ├── __init__.py     # api_router + agregación de submódulos
│       ├── common.py       # Helpers: índice de series, rutas seguras
│       ├── dependencies.py # Dependencias FastAPI (get_source)
│       ├── content.py      # Detalles y capítulos (local/remoto)
│       ├── downloads.py    # Cola de descargas
│       ├── library.py      # Biblioteca y estados
│       ├── media.py        # Streaming y portadas
│       ├── progress.py     # Progreso de lectura/visionado
│       ├── scraper_configs.py  # CRUD de fuentes dinámicas
│       ├── scraper_tester.py   # Testeo y auto-configuración de scrapers
│       ├── search.py       # Búsqueda (simple, todas, SSE)
│       ├── settings.py     # Configuración de fuentes habilitadas
│       ├── updates.py      # Comprobación de capítulos nuevos
│       └── watched.py      # Capítulos vistos y borrado de contenido
│
├── templates/              # Jinja2: base, index, serie, reader, settings
├── static/                 # CSS/JS/fuentes + dist/ (bundles hasheados)
│   └── dist/build.json     # Manifiesto de bundles generado por scripts/build.py
├── scripts/
│   └── build.py            # Build del frontend (bundles + hashes) → [[Desarrollo]]
├── tests/                  # Tests de html_utils y selector_detector
├── cache/                  # Caché en disco (JSON hasheados md5)
├── data.db                 # BD SQLite (raíz, compatibilidad)
└── docs/                   # Esta documentación (vault de Obsidian)
```

---

## Dependencias clave (`requirements.txt`)

| Paquete | Uso |
|---|---|
| `fastapi` + `uvicorn[standard]` | Servidor web |
| `requests` + `cloudscraper` | HTTP con bypass de Cloudflare |
| `beautifulsoup4` | Parseo HTML |
| `yt-dlp` | Resolución de enlaces (Mp4upload en JKanime) |
| `pycryptodome` | Criptografía auxiliar |
| `pydantic` / `pydantic-settings` | Modelos y configuración |
| `rcssmin` / `rjsmin` | Minificación del build frontend |
| `ffmpeg` (binario, no pip) | faststart de vídeo y thumbnails |

---

## Notas relacionadas
- [[Arquitectura]]
- [[Modelo de Datos]]
- [[Fuentes]]
- [[Desarrollo]]
