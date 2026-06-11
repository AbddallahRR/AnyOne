# Plan de Optimización para AnyOne

Se identificaron ~30 oportunidades de optimización en 4 áreas.

---

## P0 — Bugs de rendimiento (corrigen comportamiento incorrecto)

### 1. `api_search_all_stream` busca fuentes secuencialmente
**`routers/api/search.py:147-169`**

Las corutinas se crean pero no se envuelven en `asyncio.create_task()`. Se iteran y await one-by-one, por lo que la fuente 2 no empieza hasta que termina la fuente 1.

**Fix:** Envolver cada corutina con `asyncio.create_task()` y usar `asyncio.wait(..., return_when=FIRST_COMPLETED)`.

### 2. `extract_items_with_templates` serializa + re-parsea HTML completo
**`core/html_utils.py:103`**

`soup_copy = BeautifulSoup(str(soup), 'html.parser')` convierte el árbol BeautifulSoup a string y lo re-parsea. Se llama en cada búsqueda/capítulo/test.

**Fix:** Usar `copy.copy(soup)` para clonar el árbol en memoria sin serialización.

### 3. `_load_bundles()` lee disco en cada request HTTP
**`routers/pages.py:15-25`**

Cada ruta reabre y re-parsea `static/dist/build.json`. Hasta 5 lecturas por página.

**Fix:** Cachear el manifiesto en variable global con lazy loading.

### 4. Acumulación de event listeners
- `static/js/app.js:334-347`: `renderSearchResults()` agrega click listener sin remover.
- `static/js/reader.js:461,508`: `loadMangaChapter()` e `init()` agregan `beforeunload` listeners sin remover anteriores.

**Fix:** named functions + `removeEventListener` o `{ once: true }`.

---

## P1 — Alto impacto, esfuerzo medio

### 5. Índices faltantes en SQLite (4 índices)
- `download_queue (content_ref, status)` — full scan en cada encolado (`common.py:98-106`)
- `series_status (status, last_checked_at)` — escanea filas sin índice (`database.py:401-412`)
- `series_status (new_chapters_found)` — full scan en `/library/updates` (`database.py:457-459`)
- `download_queue (status, created_at)` — sort externo en `/queue/status` (`common.py:124-133`)
- Además: expresión `strftime... >= ?` no es sargable; cambiarla a comparación directa.

### 6. `DynamicSource._load_config()` hace 4-6 SELECTs por request
**`sources/dynamic.py:52-110`**

Cada propiedad (`label`, `type`, `BASE_URL`, etc.) llama a `_load_config()` independientemente.

**Fix:** Cachear `_cfg` en memoria con generation counter.

### 7. Descarga secuencial de imágenes en 5 fuentes manga
`dynamic.py:640-658`, `nartag.py:411-427`, `ikigai.py:500-514`, `manhwaweb.py:149-166`, `olympus.py:421-437`

40+ imágenes por capítulo x 2s rate limit = 80+ segundos.

**Fix:** `ThreadPoolExecutor(max_workers=3-4)` respetando rate limiter.

### 8. `scan_downloaded_series` — lock gap + TTL bajo
**`core/utils.py:113-136`**

- TTL 60s: rescanea árbol completo cada minuto
- Lock solo cubre TTL check y writeback, no el escaneo en sí

**Fix:** Extender lock al escaneo completo. TTL a 300s o usar inotify.

### 9. IntersectionObserver leaks en `animateCards`
- `base.html:55-71`: crea nuevo observer en cada llamada, nunca disconnect()
- `serie.html:133-135`: MutationObserver redundante (serie.js ya llama animateCards)

**Fix:** WeakMap keyed by container. Eliminar MutationObserver del template.

### 10. N+1 en `api_library_updates()`
**`routers/api/library.py:190-207`**

SELECT individual por cada serie con updates.

**Fix:** `SELECT id, title FROM content WHERE id IN (?,?,...)`.

---

## P2 — Impacto medio, esfuerzo bajo

### 11. CSS-in-JS injection (render-blocking)
`queue-indicator.js:6-208` y `scraper-health.js:6-193` — ~200 líneas de CSS inyectadas via `<style>`.

**Fix:** Mover a archivos CSS dedicados via `<link>`.

### 12. `patchPillInDOM` reemplaza elemento entero
`serie.js:282-294`: innerHTML + replaceWith para solo cambiar clase/toggle watched.

**Fix:** `classList.toggle()` + textContent update.

### 13. `api_delete_watched` hace N transacciones
`library.py:113-146`: cada delete_watched_chapter() es su propia transacción.

**Fix:** `DELETE ... WHERE content_id = ? AND chapter_number IN (...)`.

### 14. Sin caché server-side para ffprobe duration
`content.py:294-306`: subprocess.run por cada request.

**Fix:** lru_cache keyed por (ruta, mtime).

### 15. AnimeFLV (IGNORE'd) se importa completamente en startup
`sources/animeflv.py`: 654 líneas, cloudscraper + bs4 importados antes de detectar IGNORE.

**Fix:** Leer archivo como texto antes de importar, o eliminar archivo muerto.

### 16. `_warm_all_sources()` timeout inefectivo
`app.py:69-85`: timeout de 30s en funciones que retornan inmediatamente (spawn thread).

**Fix:** Remover timeout o poner timeout global en gather().

### 17-20. CSS/Frontend cleanup
- `@keyframes spin` duplicado en `settings.css:832-834`
- Dead CSS `.download-indicator` en base.css y reader.css
- Archivos TTF no usados (~330KB) en static/fonts/
- Fallback silencioso cuando falta minificador en build.py

---

## P3 — Bajo impacto

### 21. `save_content_to_db()` llamado 2 veces por descarga
(downloads.py + download_worker.py)

### 22. IkigaiSource crea ThreadPoolExecutor repetidamente
(ikigai.py:235)

### 23. DynamicSource.__init__() crea cloudscraper eager
(dynamic.py:49)

### 24. SOURCES mutations no thread-safe
(sources.py:84,87,182)

### 25. DB queries durante module import (antes de init_db)
(sources.py:127-131)

---

## Resumen

| Categoría | Items | Esfuerzo |
|---|---|---|
| P0 — Bugs | #1-#4 | 1-2 días |
| P1 — Alto impacto | #5-#10 | 3-5 días |
| P2 — Medio impacto | #11-#20 | 2-3 días |
| P3 — Bajo impacto | #21-#25 | 1 día |

**Total estimado: ~7-11 días hábiles.**

P0 corrige comportamiento incorrecto (búsqueda en serie, parsing ineficiente, file I/O excesivo, memory leaks). P1 rinde mayor beneficio en tiempo de respuesta y reducción de I/O: índices de BD, caching de config de scrapers dinámicos, paralelización de descargas de imágenes.