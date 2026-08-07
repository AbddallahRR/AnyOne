---
tags: [anyone, desarrollo, tests, lint, build]
tema: any
estado: activo
descripcion: Herramientas de desarrollo, testing y build del frontend
---

# Desarrollo

## Lint y formato

Configuración en `pyproject.toml`:

- **ruff** — línea 120, target py311, reglas `E/F/W/I`.
- **mypy** — py311, `ignore_missing_imports = true`.

```bash
ruff check .
mypy .
```

## Tests

Ubicados en `tests/`:

- `test_html_utils.py` — utilidades DOM/imágenes.
- `test_selector_detector.py` — auto-detección de selectores.

```bash
pytest
```

## Build del frontend

`scripts/build.py` (Python puro, sin Node/npm):

1. **CSS:** bundle compartido `shared` (`inter.css + fa-subset.css + base.css + layout.css`) + un bundle por página (`index`, `serie`, `reader`, `settings`).
2. **JS:** un bundle por página (`index`, `serie`, `reader`, `settings`) con sus dependencias.
3. Minifica con `rcssmin`/`rjsmin` (si no están, deja el código sin minificar).
4. Genera nombres con **hash de contenido** (`nombre.<sha256[:12]>.ext`) y el manifiesto `static/dist/build.json`.
5. Limpia bundles obsoletos (`clean_dist()`).

```bash
python scripts/build.py
```

> El manifiesto `build.json` es leído por `routers/pages.py` (`_load_bundles()`) para inyectar las URLs con hash en las plantillas. Hay que re-ejecutar el build tras cambiar CSS/JS.

## Convenciones del código

- Mensajes de log y de error de la API en **español**.
- Modelos de dominio y de API en `core/models.py` (Pydantic).
- Las fuentes implementan métodos `*_sync`; la versión async es un wrapper automático (ver [[Fuentes]]).
- Import lazy (dentro de las funciones) para evitar ciclos y para no acoplar el import de fuentes a la BD.

---

## Notas relacionadas
- [[Estructura del Proyecto]]
- [[Arquitectura]]
