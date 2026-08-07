---
tags: [anyone, instalacion, despliegue, docker]
tema: any
estado: activo
descripcion: Instalación local y despliegue con Docker
---

# Instalación y Despliegue

## Requisitos

- **Python ≥ 3.11**
- **ffmpeg** (post-proceso `faststart` y thumbnails WebP)
- **curl** (descargas de algunos hosts en JKanime)
- **yt-dlp** (resolución de Mp4upload) — instalado vía `requirements.txt`

---

## Instalación local

```bash
git clone <repo> AnyOne
cd AnyOne

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Build del frontend (bundles hasheados en static/dist/)
python scripts/build.py

# Arranque en desarrollo
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

La app queda en `http://localhost:5000`. Comprobación de salud: `GET /health` → `{"status": "ok"}`.

> Si `scripts/build.py` no se ejecuta, la UI no encontrará los bundles (`static/dist/build.json`).

---

## Despliegue con Docker

El `Dockerfile` usa build multi-etapa: compila las dependencias con headers de C en un builder y copia solo el resultado a una imagen `python:3.12-slim` con `ffmpeg` y `curl`.

```bash
docker compose up -d --build
```

### `docker-compose.yml`

- Puerto `5000:5000`
- Volúmenes:
  - `~/DescargasComics:/data/descargas`
  - `~/.config/comic_web:/data/config`
  - `~/.config/comic_web/cache:/app/cache`
- Variables: `BASE_DOWNLOAD_DIR=/data/descargas`, `DB_DIR=/data/config`, `DEBUG=false`
- `restart: unless-stopped`
- `ulimits nofile: 65536`

### `entrypoint.py` (contenedor)

Antes de lanzar uvicorn:

1. Detecta UID/GID del volumen montado (para escritura de descargas).
2. Hace `chown` recursivo de `sources/` y `cache/` a ese usuario.
3. Baja privilegios (`setgid`/`setuid` a 1000) y ejecuta el comando real.

---

## Migración a otro servidor

La guía original (`docs/guia_docker.txt`) describe exportar la imagen a un archivo y cargarla en el destino:

```bash
# Origen
docker compose up -d --build
docker save -o comic-web.tar anyone-anyone

# Destino
docker load -i /srv/nas/comic-web.tar
cd /srv/comic-web/
docker compose up -d
```

### Qué llevar en el backup

- **Datos:** `~/.config/comic_web/` (BD `history.db` + configs de scraper)
- **Contenido:** `~/DescargasComics/` (las series descargadas)
- **Caché (opcional):** `~/config/comic_web/cache` — se puede regenerar

---

## Notas relacionadas
- [[Configuración]]
- [[Estructura del Proyecto]]
- [[Arquitectura]]
