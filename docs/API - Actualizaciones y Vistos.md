---
tags: [anyone, api, actualizaciones, vistos, borrado]
tema: any
estado: activo
descripcion: Endpoints de comprobación de capítulos nuevos, capítulos vistos y borrado
---

# API - Actualizaciones y Vistos

## Comprobación de actualizaciones

### `POST /api/library/check-updates/{content_ref:path}`
Comprueba una serie concreta buscando **capítulos nuevos** y los encola automáticamente.

- Para refs `local:` lee `series_info.json` (fuente + `content_id`); para refs remotas localiza la carpeta en disco.
- Limpia caché de capítulos/búsqueda, consulta capítulos remotos y compara contra el máximo local (`chapter_float_key`).
- Actualiza `last_checked_at` y `new_chapters_found`; encola cada capítulo nuevo (omite los ya activos en cola).
- Respuesta: `{content_ref, new_chapters, new_chapter_ids, total_remote, total_local, queued, error}`.
- Si `error` está presente → `500`.

### `POST /api/library/check-all-updates`
Comprueba **todas** las series pendientes (pool de 4 hilos).

- Solo series con estado `watching`/`completed` cuya `last_checked_at` tenga ≥ 24 h (`get_series_to_check`).
- Respuesta: resumen agregado `{checked, with_updates, ...}`.

> El **scheduler diario** de `app.py` ejecuta `_check_all_updates_core()` cada día a las 10:00 y limpia los avisos antes de comprobar.

---

## Capítulos vistos

### `POST /api/watched`
Marca un capítulo como visto.

- **Body** (`WatchedToggleRequest`): `content_ref`, `chapter`.

### `GET /api/watched/{content_ref:path}`
Lista de capítulos vistos de una serie.

### `POST /api/watched/toggle`
Alterna visto/no visto; devuelve `watched` o `unwatched`.

---

## Borrado de contenido

Todos los borrados exigen refs **locales** (`local:`) → si no, `400`.

### `POST /api/delete-watched`
Borra los **archivos** de todos los capítulos vistos de una serie.

- **Body** (`DeleteWatchedRequest`): `content_ref`, `type`.
- Omite el capítulo que coincide con el progreso actual (último) y los que se están descargando.
- Borra en lote las filas de `watched_chapters`.

### `POST /api/delete-chapter`
Borra **un capítulo** concreto.

- **Body** (`DeleteChapterRequest`): `content_ref`, `type`, `chapter`.
- `409` si se está descargando.
- Si borra el último capítulo, recalcula el máximo restante y actualiza el progreso.

### `POST /api/delete-series`
Borra la **serie completa** (carpeta + filas BD + caché).

- **Body** (`DeleteSeriesRequest`): `content_ref`, `type`.
- Elimina `user_progress`, `watched_chapters`, `series_status`, `content` y `download_queue`, además de `shutil.rmtree` de la carpeta.
- Invalida el índice de series y la caché de escaneo.

---

## Notas relacionadas
- [[API]]
- [[API - Biblioteca y Progreso]]
- [[Modelo de Datos]]
