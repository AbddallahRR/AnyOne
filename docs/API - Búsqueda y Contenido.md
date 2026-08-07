---
tags: [anyone, api, busqueda, contenido]
tema: any
estado: activo
descripcion: Endpoints de búsqueda, detalles y capítulos
---

# API - Búsqueda y Contenido

## Búsqueda

### `GET /api/search`
Buscar en una fuente concreta.

- **Query params:** `type` (anime/manga), `source`, `q`, `refresh` (bool).
- **Respuesta:** lista de [[Modelo de Datos|SearchResult]] enriquecida con `last_chapter` y `progress` de la BD (normaliza números quitando ceros a la izquierda).
- **Caché:** clave `search:{type}:{source}:{q}`.

### `GET /api/search-all`
Buscar en **todas** las fuentes habilitadas de un tipo (concurrente).

- **Query params:** `type`, `q`, `refresh`.
- Deduplica por `source:id` y ordena por título.
- La clave de caché incluye una *huella* de las fuentes habilitadas (cambiar fuentes invalida la caché).

### `GET /api/search-all-stream`
Streaming **SSE** de búsqueda en todas las fuentes.

- Eventos: `results` (por fuente, según termina), `source_error` (fuente desactivada), `done`.
- Timeout por fuente: 90 s.
- Cabecera `X-Accel-Buffering: no`.
- Registra éxito/fallo por fuente en `scraper_health` (ver [[API - Configuración de Fuentes]]).

---

## Contenido

### `GET /api/content/{content_type}/{source}/{content_id}`
Detalles de una serie remota.

- **Query param:** `refresh`.
- Caché: `details_cache`.
- Persiste el resultado en la tabla `content`.

### `GET /api/content/local/{type}/{id}`
Detalles de una serie **local** (lee `series_info.json` y detecta portada/thumb).

### `GET /api/chapters/{content_type}/{source}/{content_id}`
Capítulos de una serie remota.

- **Query param:** `refresh`.
- Caché: `chapters_cache` y `search_cache`.

### `GET /api/chapters/local/{type}/{id}`
Capítulos locales (`.mp4` en anime, carpetas `cap_*` en manga).

### `GET /api/chapters/with-local/{type}/{source}/{content_id}`
Capítulos remotos **anotados** con `is_downloaded` (comparando contra lo descargado).

### `POST /api/cache/clear/{content_type}/{source}/{content_id}`
Limpia la caché (detalles + capítulos + búsqueda) de un ítem concreto.

---

## Errores típicos

- Fuente/serie desconocida → `404`.
- Fallo al obtener datos remotos → `500` con mensaje genérico (la causa real queda en los logs).

---

## Notas relacionadas
- [[API]]
- [[Fuentes]]
- [[Modelo de Datos]]
