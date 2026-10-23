# AnyOne

Agregador y descargador **self-hosted** de anime y manga. Busca series en distintas fuentes, las descarga, organiza la biblioteca en disco y sirve el contenido descargado como streaming o lector local desde una interfaz web.

- **Backend:** Python ≥ 3.11 + FastAPI (uvicorn)
- **Base de datos:** SQLite (WAL)
- **Frontend:** plantillas Jinja2 + JS vanilla, empaquetado con `scripts/build.py`
- **Despliegue:** local o Docker

## Funcionalidades

| Área | Detalle |
|---|---|
| Búsqueda | Por fuente, en todas las habilitadas o en streaming (SSE) |
| Descargas | Serie completa, capítulos sueltos o por lotes, con cola persistente |
| Biblioteca | Series descargadas escaneadas del disco y estados (`watching`, `completed`, `pending`, `none`) |
| Progreso | Seguimiento por serie y capítulo, capítulos vistos |
| Media | Streaming local con *range requests*, lector de manga y streaming remoto |
| Fuentes | JKanime (anime), Ikigai (manga) y scrapers dinámicos configurables desde la UI |
| Actualizaciones | Comprobación programada de capítulos nuevos por serie |

## Arranque local

Requisitos: **Python ≥ 3.11**, **ffmpeg** y **curl**.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Genera los bundles del frontend en static/dist/
python scripts/build.py

uvicorn app:app --host 0.0.0.0 --port 5000
```

La app queda en `http://localhost:5000`. Salud: `GET /health` → `{"status": "ok"}`.

> Sin `scripts/build.py` no existe `static/dist/build.json` y la UI no carga sus estilos ni scripts.

## Docker

```bash
docker compose up -d --build
```

`docker-compose.yml` publica el puerto `5000` y monta:

| Host | Contenedor | Uso |
|---|---|---|
| `~/DescargasComics` | `/data/descargas` | Anime y manga descargados |
| `~/.config/comic_web` | `/data/config` | Base de datos y configuraciones |
| `~/.config/comic_web/cache` | `/app/cache` | Caché de disco (regenerable) |

El `Dockerfile` es multi-etapa e incluye `ffmpeg` y `curl`. `entrypoint.py` ajusta permisos de los volúmenes y ejecuta el proceso con el UID/GID del host.

## Configuración

Todas las opciones de `core/settings.py` se sobrescriben con variables de entorno:

| Variable | Por defecto | Descripción |
|---|---|---|
| `BASE_DOWNLOAD_DIR` | `~/DescargasComics` | Raíz de descargas (`Anime/` y `Manga/`) |
| `DB_DIR` | `~/.config/comic_web` | Directorio de `history.db` |
| `SECRET_KEY` | clave insegura de desarrollo | Cámbiala en producción |
| `DEBUG` | `false` | Recarga automática de uvicorn |
| `HOST` / `PORT` | `0.0.0.0` / `5000` | Interfaz y puerto |
| `DOWNLOAD_NUM_WORKERS` | `3` | Descargas en paralelo |
| `CORS_ORIGINS` | `*` | Orígenes separados por coma |

Las fuentes activas se gestionan desde **Ajustes → Fuentes** o con `GET/PUT /api/settings/sources`.

## Estructura

```
app.py              Entrada FastAPI (lifespan, middlewares, /health)
core/               Configuración, BD, caché, workers, scraping compartido
sources/            Fuentes de contenido (una clase por sitio)
routers/            Rutas HTML (pages.py) y API REST (/api)
templates/ static/  UI Jinja2, CSS/JS y bundles generados
scripts/build.py    Build del frontend (bundles hasheados + manifiesto)
tests/              Tests de pytest
docs/               Documentación detallada (vault de Obsidian)
```

## Desarrollo

```bash
pytest              # tests
ruff check .        # lint
mypy .              # tipado
python scripts/build.py  # re-ejecutar tras cambiar CSS/JS
```

## Documentación

Índice completo en [`docs/AnyOne - Inicio.md`](<docs/AnyOne - Inicio.md>). Destacan:

- [`docs/Arquitectura.md`](docs/Arquitectura.md) — procesos, concurrencia y caché
- [`docs/Configuración.md`](<docs/Configuración.md>) — variables y ajustes internos
- [`docs/Instalación y Despliegue.md`](<docs/Instalación%20y%20Despliegue.md>) — instalación, Docker y backups
- [`docs/API.md`](docs/API.md) — API REST bajo `/api`
- [`docs/Fuentes.md`](docs/Fuentes.md) — cómo funciona una fuente y cómo añadir una
- [`docs/Modelo de Datos.md`](<docs/Modelo%20de%20Datos.md>) — esquema SQLite

## Aviso

AnyOne no aloja contenido: scrapea sitios de terceros. Úsalo solo para contenido al que tengas derecho de acceso y respeta las condiciones de cada sitio y la legislación de tu país.
