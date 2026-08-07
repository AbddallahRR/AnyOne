---
tags: [anyone, base-de-datos, sqlite, esquema]
tema: any
estado: activo
descripcion: Esquema SQLite, tablas y sistema de migraciones
---

# Modelo de Datos

La base de datos es **SQLite en modo WAL** (`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=60s`, `foreign_keys=ON`). Cada hilo usa una conexión propia (`threading.local` en `core/db/connection.py`). Los `UPDATE`/`INSERT` se reintentan hasta 6 veces con *backoff* exponencial si la BD está bloqueada.

## Ubicación

- `settings.db_path` → `DB_DIR/history.db` (por defecto `~/.config/comic_web/history.db`)

---

## Tablas

### `schema_version`
Registra la versión del esquema (actual: **12**).

### `content`
Metadatos de series consultadas (upsert).

| Columna | Tipo | Notas |
|---|---|---|
| `id` | TEXT | PK → `source:content_id` |
| `type` | TEXT | `anime` / `manga` |
| `source` | TEXT | nombre de la fuente |
| `content_id` | TEXT | id en la fuente |
| `title` | TEXT | título |
| `cover` | TEXT | portada |

### `user_progress`
Progreso por serie.

| Columna | Tipo |
|---|---|
| `content_id` | TEXT PK (`local:{id}` o `{source}:{content_id}`) |
| `chapter` | TEXT (por defecto `1`) |
| `progress` | TEXT (por defecto `0`) |
| `updated_at` | TIMESTAMP |

Índice compuesto para `get_recent_progress()`.

### `download_queue`
Cola persistida de descargas.

| Columna | Tipo |
|---|---|
| `id` | INTEGER PK AUTOINCREMENT |
| `content_ref` | TEXT |
| `type` | TEXT |
| `title` | TEXT |
| `chapter_id` | TEXT nullable |
| `status` | TEXT: `pending` / `downloading` / `completed` / `failed` |
| `total_chapters` / `current_chapter` / `current_progress` | INTEGER |
| `error` | TEXT |
| `created_at` | TIMESTAMP |

### `watched_chapters`
Capítulos marcados como vistos.

| Columna | Tipo |
|---|---|
| `id` | INTEGER PK |
| `content_id` | TEXT |
| `chapter_number` | TEXT (soporta decimales, migración 8) |
| `watched_at` | TIMESTAMP |
| | UNIQUE(`content_id`, `chapter_number`) |

### `series_status`
Estados de biblioteca y comprobación de actualizaciones.

| Columna | Tipo |
|---|---|
| `content_ref` | TEXT PK |
| `status` | TEXT: `watching` / `completed` / `pending` / `none` |
| `updated_at` | TIMESTAMP |
| `last_checked_at` | TIMESTAMP |
| `new_chapters_found` | TEXT (JSON de capítulos nuevos) |

### `source_settings`
Fuentes habilitadas/deshabilitadas.

| Columna | Tipo |
|---|---|
| `name` | TEXT PK |
| `type` | TEXT |
| `enabled` | INTEGER |

### `scraper_configs`
Configuraciones de scrapers (incluye las built-in). → [[Fuente - Dinámica]]

| Columna | Tipo |
|---|---|
| `name` | TEXT PK |
| `type` | TEXT |
| `label` | TEXT |
| `base_url` | TEXT |
| `built_in` | INTEGER |
| `enabled` | INTEGER |
| `config_json` | TEXT (config del scraper) |
| `created_at` / `updated_at` | REAL |

---

## Migraciones

`core/db/connection.py` define `SCHEMA_VERSION = 12` y migraciones incrementales:

| Versión | Cambio |
|---|---|
| 1 | Tablas base (`content`, `user_progress`, `download_queue`, `watched_chapters`) |
| 2 | `download_queue.chapter_id`, `content_ref` |
| 3 | `series_status` |
| 4 | `series_status.last_checked_at` |
| 5 | `series_status.new_chapters_found` |
| 6 | `source_settings` |
| 7 | `scraper_configs` + seeds built-in (jkanime, nartag, manhwaweb, ikigai) |
| 8 | `watched_chapters.chapter_number` → TEXT (decimales) |
| 9 | Índices de rendimiento en cola y estados |
| 10 | `user_progress.updated_at` |
| 11 | Índice compuesto en `user_progress` |
| 12 | Elimina fuentes obsoletas `nartag` y `manhwaweb` |

### Limpieza al arrancar

`cleanup_download_queue()` marca los trabajos `pending`/`downloading` como `failed` ("Interrumpido por reinicio del servidor") y elimina archivos parciales de capítulos (`.mp4` en anime, carpetas `cap_*` en manga).

---

## Notas relacionadas
- [[Arquitectura]]
- [[Estructura del Proyecto]]
- [[Configuración]]
