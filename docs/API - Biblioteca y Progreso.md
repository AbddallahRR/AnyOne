---
tags: [anyone, api, biblioteca, progreso]
tema: any
estado: activo
descripcion: Endpoints de biblioteca, estados y progreso
---

# API - Biblioteca y Progreso

## Biblioteca

### `GET /api/library`
Lista las series **descargadas** (escaneo del disco, con caché de 5 min) + `recent` (últimos 10 progresos).

### `GET /api/library/recent`
Solo la lista de recientes.

### `GET /api/library/status`
Mapa `content_ref → status` de toda la biblioteca.

### `GET /api/library/status/{content_ref:path}`
Estado de una serie concreta.

### `POST /api/library/status`
Cambiar estado.

- **Body** (`StatusUpdateRequest`): `content_ref`, `status` ∈ `watching | completed | pending | none`.
- `none` borra la fila de `series_status`.

### `GET /api/library/updates`
Series con **capítulos nuevos** detectados (resuelve título local y ruta).

### `POST /api/library/acknowledge-updates`
Confirma/limpia los avisos de capítulos nuevos.

- **Body:** `content_ref` o `content_refs` (lista). Si falta ambos → `400`.

---

## Progreso

### `GET /api/progress/local/{type}/{id}`
Progreso de una serie local (`local:{id}`). Devuelve `{chapter, progress}`.

### `POST /api/progress/local/{type}/{id}`
Guardar progreso local.

### `GET /api/progress/{content_type}/{source}/{content_id}`
Progreso de una serie remota (`{source}:{content_id}`).

### `POST /api/progress/{content_type}/{source}/{content_id}`
Guardar progreso remoto.

- **Body** (`ProgressRequest`): `chapter` (def. `1`), `progress` (def. `0`). Acepta números (los coerces a string).

---

## Datos extra por serie

`_get_chapter_total()` (en `library.py`) calcula el total de capítulos: cuenta imágenes en manga o la **duración del vídeo** (vía ffprobe, cacheada) en anime. Para duraciones ver [[API - Media y Streaming]].

---

## Notas relacionadas
- [[API]]
- [[Modelo de Datos]]
