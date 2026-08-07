---
tags: [anyone, configuracion, entorno]
tema: any
estado: activo
descripcion: Variables de entorno y opciones de configuración
---

# Configuración

La configuración se define en `core/settings.py` usando `pydantic-settings`. Todas las variables son **sobrescribibles por variables de entorno** (mismo nombre, sin prefijo).

## Variables disponibles

| Variable | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `BASE_DOWNLOAD_DIR` | Path | `~/DescargasComics` | Raíz de descargas. De ahí salen `Anime/` y `Manga/` |
| `DB_DIR` | Path | `~/.config/comic_web` | Directorio de la BD (`history.db`) |
| `SECRET_KEY` | str | `insecure-dev-key-change-in-production` | Clave de la app (cámbiala en producción) |
| `DEBUG` | bool | `false` | Activa `reload` de uvicorn |
| `HOST` | str | `0.0.0.0` | Interfaz de escucha |
| `PORT` | int | `5000` | Puerto HTTP |
| `DOWNLOAD_NUM_WORKERS` | int | `3` | Nº de descargadores en paralelo |
| `CORS_ORIGINS` | str | `*` | Orígenes CORS separados por coma |

## Propiedades derivadas

- `anime_download_dir` → `BASE_DOWNLOAD_DIR/Anime`
- `manga_download_dir` → `BASE_DOWNLOAD_DIR/Manga`
- `db_path` → `DB_DIR/history.db`
- `cors_origin_list` → lista de orígenes a partir de `CORS_ORIGINS`

---

## Ajustes no configurables

- **Scheduler diario:** comprobación de actualizaciones a las **10:00**, limpieza de caché cada 24 h (`app.py`).
- **Rate limiter:** 1 s de intervalo mínimo por dominio (`core/throttle.py`).
- **Timeouts HTTP:** 30 s (`core/http_pool.py`).
- **Circuit breaker:** una fuente se desactiva temporalmente tras 3 fallos consecutivos durante 5 minutos (`core/scraper_health.py`).
- **Cola de descargas:** máx. 50 trabajos en memoria (`core/download_worker.py`).

---

## Configuración de fuentes habilitadas

Las fuentes activas se gestionan en la tabla `source_settings` (ver [[Modelo de Datos]]). Desde la UI: *Ajustes → Fuentes*. Desde API: `GET/PUT /api/settings/sources` (ver [[API - Configuración de Fuentes]]).

## Ejemplo

```bash
export SECRET_KEY="mi-clave-segura"
export BASE_DOWNLOAD_DIR="/srv/media/descargas"
export DB_DIR="/srv/media/config"
export DEBUG=true
uvicorn app:app --host 0.0.0.0 --port 5000
```

---

## Notas relacionadas
- [[Arquitectura]]
- [[Instalación y Despliegue]]
- [[Modelo de Datos]]
