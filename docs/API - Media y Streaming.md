---
tags: [anyone, api, media, streaming, portadas]
tema: any
estado: activo
descripcion: Endpoints de portadas, reproducción y duración
---

# API - Media y Streaming

## Portadas

### `GET /api/local-cover/{type}/{filename:path}`
Sirve la portada de una serie local.

- **Query param:** `thumb=1` → sirve `thumb.webp` (miniatura).
- Rutas validadas contra *path traversal* (`_safe_path`).

## Reproducción

### `GET /api/play/local/{type}/{id}/{chapter}`
Reproducir capítulo **local**:

- **Anime:** sirve el `.mp4` con soporte **HTTP Range** (206 parcial), `ETag`/`If-None-Match` (304) y `Accept-Ranges: bytes`. Chunk 64 KB, caché 1 día.
- **Manga:** devuelve la lista de rutas de imágenes del capítulo.

### `GET /api/play/{content_type}/{source}/{content_id}/{chapter}`
Reproducir capítulo de una serie **descargada** (se busca la serie local por índice y se sirve el archivo).

### `GET /api/play/remote/{content_type}/{source}/{content_id}/{chapter}`
Streaming **remoto** sin descargar:

- **Anime:** `get_stream_url()` → `{url, type:'embed'}` (iframe del servidor de la fuente). Requiere `supports_streaming`.
- **Manga:** `get_chapter_images()` → URLs de imágenes filtradas con `filter_manga_images(min_dimension=300)` (descarta logos/placeholders/thumbnails pequeños).

### `GET /api/manga/images/{subpath:path}`
Sirve un archivo de imagen de manga local (ruta segura).

## Utilidades

### `GET /api/video-duration/anime/{content_id}/{chapter}`
Duración del vídeo mediante **ffprobe** (timeout 10 s), cacheada con `lru_cache(256)`.

---

## Detalles de implementación

- `_serve_video()` en `routers/api/media.py` implementa el rango manualmente.
- La búsqueda de archivos de anime acepta patrones de nombre: `{título}_{cap}.mp4`, `{cap:03d}.mp4`, `{cap}.mp4`, etc.
- `supports_streaming`: JKanime devuelve `true` (anime); el manga siempre usa imágenes. Ver [[Fuente - JKanime]] y [[Fuente - Dinámica]].

---

## Notas relacionadas
- [[API]]
- [[API - Búsqueda y Contenido]]
- [[Fuente - JKanime]]
