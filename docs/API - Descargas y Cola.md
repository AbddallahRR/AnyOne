---
tags: [anyone, api, descargas, cola]
tema: any
estado: activo
descripcion: Endpoints de cola de descarga y jobs
---

# API - Descargas y Cola

## Cola de descargas

### `GET /api/queue/status`
Estado de la cola: trabajos **activos** + **pendientes**, ordenados por creación (desde la tabla `download_queue`).

### `POST /api/download`
Descargar una **serie completa**.

- **Body** (`DownloadRequest`): `type`, `source`, `content_id`, `title`, `exclude_watched` (bool).
- Si `exclude_watched` es `true`, se excluyen los capítulos vistos para `local:{título normalizado}`.
- Persiste el trabajo en BD y lo encola en memoria.
- Errores: `409` si ya existe el trabajo pendiente/descargándose, `503` si la cola está llena (máx. 50).

### `POST /api/download/chapter`
Descargar un **capítulo concreto** (`DownloadChapterRequest`).

### `POST /api/download/chapters`
Descargar un **lote** de capítulos (`DownloadChaptersRequest`, `chapter_ids[]`).

- Respuesta: `{job_ids, count, message}`; omite capítulos ya encolados.

---

## Cómo funciona el worker

`core/download_worker.py`:

1. Los hilos descargadores (`download_num_workers`) consumen `download_queue` (columna `download_queue` de BD + `queue.Queue` en memoria).
2. Para cada trabajo:
   - Resuelve los capítulos (`_resolve_chapters`) filtrando excluidos.
   - Crea la carpeta de la serie (`Anime/` o `Manga/`) y guarda metadatos + portada (`series_info.json`, `cover.*`, `thumb.webp`).
   - Descarga cada capítulo llamando a la fuente; reintenta hasta 3 intentos con *backoff* (`2s`, `4s`).
   - Anime: tras descargar, el `.mp4` pasa a **post-proceso ffmpeg** (`+faststart`) en un pool de 2 hilos.
   - Actualiza el progreso en BD cada 30 s o al terminar.
3. Estado `failed` con `error` si el trabajo falla; se limpia el capítulo parcial.

### Trabajos interrumpidos
Al reiniciar la app, `cleanup_download_queue()` marca pendientes/descargando como `failed` y borra archivos parciales (ver [[Modelo de Datos]]).

---

## Modelos relacionados

- `DownloadRequest`, `DownloadChapterRequest`, `DownloadChaptersRequest`, `DownloadJob` → `core/models.py`.

---

## Notas relacionadas
- [[API]]
- [[Arquitectura]]
- [[Modelo de Datos]]
