---
tags: [anyone, fuentes, scraper, dinamica, configuracion]
tema: any
estado: activo
descripcion: Motor de scrapers configurables (fuentes dinámicas)
---

# Fuente - Dinámica

El sistema de **fuentes dinámicas** permite crear scrapers sin escribir código: se configura un sitio en la UI (Ajustes → wizard de scraper) o por API, y AnyOne genera la fuente automáticamente.

- **Base:** `sources/dynamic.py` (clase `DynamicSource`)
- **Almacenamiento:** tabla `scraper_configs` (config JSON)
- **Stub generado:** `sources/{name}.py` con una subclase que fija `CONFIG_NAME`

## Cómo funciona

1. `core/scraper_config.py:create_config()` guarda la fila y escribe un stub:
   ```python
   from .dynamic import DynamicSource
   class MiFuenteSource(DynamicSource):
       type = 'manga'
       label = 'Mi Fuente'
       CONFIG_NAME = 'mi_fuente'
   ```
2. Se registra en caliente (`core.sources.register_dynamic_source`) → la fuente aparece en `SOURCES` sin reiniciar.
3. `update_config()` regenera el stub y hace *hot-reload* (`reload_config()`).
4. `delete_config()` borra fila, stub, registro, `source_settings`, salud y caché. Las **built-in no se borran**.
5. Al arrancar, `load_dynamic_sources()` re-registra todas las configs no built-in.

## Pipeline por etapa

| Etapa | Config involucrada |
|---|---|
| Catálogo (`has_catalog`) | `catalog_*` — páginas, ítems, paginación (`catalog_pagination_param`, hasta `catalog_max_pages`=100), caché 3 días |
| Búsqueda | `search_url_template` (GET) o `search_post_template` (POST), `search_result_selector`, selectores de título/URL/portada, `search_pagination_param` (hasta página 100), `search_cache_ttl` |
| Detalles | `details_url_template` + selectores de título/portada/sinopsis |
| Capítulos | `chapters_url_template`, `chapters_item_selector`, `chapters_num_selector`, `chapters_url_selector`, paginación |
| Imágenes | `content_page_template` + `content_image_selector` — ver estrategias abajo |
| Vídeo (streaming) | `content_type='video'` → `content_video_selector` (URL del stream) |

## Extracción de imágenes (6 estrategias)

En `get_chapter_images_sync`, en orden:

1. Selector CSS + atributo (con fallback a `src`).
2. Mismo selector probando todos los atributos lazy de `ATTR_PRIORITY` (`data-lm-orig-src`, `data-original`, `data-lazy-src`, `data-url`, `data-src`, …).
3. `<noscript>`.
4. Scripts JS: `ts_reader.run()`, estado SSR (`__NUXT__`, `__NEXT_DATA__`), `var images=[...]`, `JSON.parse`, Qwik, WordPress `madara_*`, regex amplia.
5. `background-image` (CSS + `data-background`).
6. Cualquier `<img>` con atributo prioritario (último recurso).

Todas pasan por `normalize_image_url()` (filtra placeholders/logos/`data:` y resuelve URLs relativas).

## Descarga

- Solo `content_type='image'` (el vídeo solo emite URL de stream).
- `_download_images()`: paralelo con `download_concurrency` (máx. 10 hilos), escribe `NNNN.<ext>` en `cap_<número>`, cabecera `Referer: BASE_URL` + cookies configuradas, omite archivos existentes.

## Configuración destacada

- `extra_headers` / `extra_cookies` / `use_cloudscraper`.
- Validación de selectores y de placeholders en templates (`{query}`, `{content_id}`, `{chapter_id}`).
- Herramientas de auto-detección: `core/selector_detector.py` + endpoints de testeo (ver [[API - Configuración de Fuentes]]).

---

## Notas relacionadas
- [[Fuentes]]
- [[API - Configuración de Fuentes]]
- [[Modelo de Datos]]
- [[Estructura del Proyecto]]
