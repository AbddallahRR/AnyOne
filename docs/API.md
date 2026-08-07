---
tags: [anyone, api, indice, moc]
tema: any
estado: activo
descripcion: Índice y convenciones de la API REST de AnyOne
---

# API — Resumen y convenciones

Toda la API cuelga del prefijo **`/api`** (`routers/api/__init__.py`). Las respuestas y mensajes de error están en español.

## Convenciones generales

- **Parámetros de ruta con `:` o `/`:** usan `{param:path}` (p. ej. `/api/library/status/{content_ref:path}`, `/api/watched/{content_ref:path}`).
- **Referencias de contenido (`content_ref`):**
  - Local: `local:{carpeta}` (serie en disco).
  - Remoto: `{source}:{content_id}`.
- **Caché:** las rutas remotas aceptan `?refresh=true` para saltarse la caché en disco.
- **SSE:** `/api/search-all-stream` emite eventos `text/event-stream`.

## Códigos de estado

| Código | Significado |
|---|---|
| 200 | OK |
| 400 | Validación, fuente deshabilitada o ref no local (`local:`) donde se requiere |
| 404 | Fuente o serie no encontrada |
| 409 | Trabajo duplicado en cola / capítulo descargándose / fuente ya existente |
| 500 | Error interno (con mensaje genérico) |
| 503 | Cola de descargas llena |

## Índice de endpoints

| Módulo | Nota | Rutas principales |
|---|---|---|
| [[API - Búsqueda y Contenido]] | Búsqueda, detalles, capítulos | `/api/search*`, `/api/content/*`, `/api/chapters/*` |
| [[API - Descargas y Cola]] | Cola de descarga | `/api/download*`, `/api/queue/status` |
| [[API - Biblioteca y Progreso]] | Biblioteca, estados, progreso | `/api/library*`, `/api/progress/*` |
| [[API - Media y Streaming]] | Portadas, reproducción, duraciones | `/api/local-cover/*`, `/api/play/*`, `/api/video-duration/*`, `/api/manga/images/*` |
| [[API - Configuración de Fuentes]] | Fuentes, scrapers, salud | `/api/settings/sources`, `/api/scraper-configs*`, `/api/scraper-health*` |
| [[API - Actualizaciones y Vistos]] | Capítulos nuevos, vistos, borrado | `/api/library/check*`, `/api/watched*`, `/api/delete-*` |

## Páginas (no API)

`routers/pages.py` (sin prefijo):

| Ruta | Página |
|---|---|
| `/` | Inicio / biblioteca |
| `/settings` | Ajustes (fuentes y scraper wizard) |
| `/serie/{type}/{source}/{id}` | Detalle de serie |
| `/reader/{type}/{source}/{content_id}/{chapter}` | Lector (manga) / reproductor (anime) |

---

## Notas relacionadas
- [[AnyOne - Inicio]]
- [[API - Búsqueda y Contenido]]
- [[API - Descargas y Cola]]
- [[API - Biblioteca y Progreso]]
- [[API - Media y Streaming]]
- [[API - Configuración de Fuentes]]
- [[API - Actualizaciones y Vistos]]
