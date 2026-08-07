---
tags: [anyone, api, fuentes, scrapers, configuracion]
tema: any
estado: activo
descripcion: Endpoints de configuración de fuentes, scrapers dinámicos y salud
---

# API - Configuración de Fuentes

## Fuentes habilitadas

### `GET /api/settings/sources`
Lista todas las fuentes con `name`, `type`, `label` y `enabled` (fusiona BD + metadatos descubiertos).

### `PUT /api/settings/sources`
Actualiza en bloque el estado habilitado.

- **Body:** `{nombre_fuente: bool}`.
- Fuente desconocida → `400`.

---

## Scrapers dinámicos (CRUD)

La tabla `scraper_configs` guarda configs; al crear se genera un **stub** en `sources/{name}.py` que se registra en caliente. Más detalles en [[Fuente - Dinámica]].

### `GET /api/scraper-configs`
Lista configs (built-in primero, alfabético).

### `GET /api/scraper-configs/{name}`
Detalle de una config (`404` si no existe).

### `POST /api/scraper-configs`
Crear config.

- **Body** (`CreateScraperConfigRequest`): `name`, `type`, `label`, `base_url`, `config`.
- Validaciones:
  - `name`: `^[a-z][a-z0-9_-]+$`.
  - Selectores CSS válidos (`validate_css_selector`).
  - Templates de URL con placeholders obligatorios: `{query}` (search), `{content_id}` (details/chapters), `{chapter_id}` (content).
  - `extra_headers`/`extra_cookies` se parsean de JSON string.
- Duplicado → `409`.

### `PUT /api/scraper-configs/{name}`
Actualizar (campos parciales): `label`, `base_url`, `enabled`, `config`. Regenera el stub y hace *hot-reload* de la fuente.

### `DELETE /api/scraper-configs/{name}`
Eliminar config. Las **built-in no se pueden borrar**.

---

## Testeo y auto-configuración

### `POST /api/scraper-configs/test`
Prueba en vivo de una config en una etapa (`search`, `details`, `chapters`, `content`).

- Respuesta: `html_preview`, `extracted`, `total_cards`, `warnings`.
- La etapa `content` usa varias estrategias de extracción de imágenes (CSS → atributos lazy → noscript → scripts JS → background → cualquier `img`).

### `POST /api/scraper-configs/check-url`
`HEAD` para verificar que una URL responde.

### `POST /api/scraper-configs/auto-detect`
Detecta selectores de búsqueda desde una página (`core/selector_detector.py`). Devuelve hasta 3 sugerencias con confianza.

### `POST /api/scraper-configs/detect-selectors`
Detecta selectores buscando por texto o patrón de URL (etapas `details`, `chapters`, `content`).

### `POST /api/scraper-configs/auto-configure`
Pipeline completo: search → details → chapters → config sugerida + lista de errores.

---

## Salud de fuentes (circuit breaker)

`core/scraper_health.py` desactiva temporalmente una fuente tras **3 fallos consecutivos** durante **5 minutos**.

### `GET /api/scraper-health`
Estado de salud de todas las fuentes: fallos, temporizador restante y último error.

### `POST /api/scraper-health/re-enable`
Re-habilitar manualmente una fuente desactivada.

- **Body** (`ReEnableRequest`): `name`.
- También actualiza `source_settings[name] = true`.

---

## Notas relacionadas
- [[API]]
- [[Fuentes]]
- [[Fuente - Dinámica]]
- [[Configuración]]
