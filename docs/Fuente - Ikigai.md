---
tags: [anyone, fuentes, manga, ikigai]
tema: any
estado: activo
descripcion: Fuente Ikigai — manga con catálogo en caché
---

# Fuente - Ikigai

- **Archivo:** `sources/ikigai.py`
- **Tipo:** `manga`
- **Etiqueta:** `Ikigai`
- **Base:** `https://visualikigai.treefy.online/` (catálogo en `/series/`)

## Métodos principales

- `search_sync(query)` — búsqueda por **subcadena sobre el catálogo completo** (no hay endpoint de búsqueda del sitio). El catálogo se sirve desde `ikigai:catalog` (TTL 3 días) y se refresca en segundo plano.
- `get_details_sync(content_id)` — parsea `h1` (título), `img.w-full` (portada), `p.text-gray-300`/`div.description` (sinopsis).
- `get_chapters_sync(content_id)` — capítulos paginados (`/series/{id}/?ordenar=asc&pagina=N`), selector `li.w-full a[href*="/capitulo/"]`, número extraído del `img[alt]` con regex `Capítulo (\d+(?:\.\d+)?)`.
- `get_chapter_images_sync(content_id, chapter_id)` — imágenes desde una cadena de atributos lazy (`data-src`, `data-lazy`, `data-original`, `data-url`, `src`), `<noscript>` y **fallback Qwik JSON** (regex sobre `<script type="qwik/json">` para URLs `image3.ikigaimangas.cloud...webp`).
- `download_chapter_sync(...)` — vía `MangaDownloadHelper`, con cabecera `Referer` = URL del capítulo.

## Catálogo

- `_fetch_full_catalog()`: páginas en lotes de 4 hilos (`_PAGE_WORKERS`).
- Cada worker usa su **propio scraper** (`HttpPool.get_scraper()`, cloudscraper no es thread-safe entre instancias).
- Para cuando una página devuelve 0 ítems, no hay `has_next` o se alcanza `_MAX_PAGES = 500`.
- `_refresh_catalog_background()` con cooldown de **24 h** y lock por proceso.
- `warm_cache_sync()` precarga el catálogo al arrancar.

## Notas relacionadas
- [[Fuentes]]
- [[API - Media y Streaming]]
