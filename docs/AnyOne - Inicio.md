---
tags: [anyone, inicio, indice, moc]
tema: any
estado: activo
descripcion: Nota índice del proyecto AnyOne
---

# AnyOne — Inicio

**AnyOne** es un **agregador y descargador self-hosted de anime y manga**. Expone una interfaz web para buscar series, consultar detalles y capítulos, descargar series completas (o capítulos sueltos), llevar un seguimiento de progreso y capítulos vistos, y servir el contenido descargado como streaming local.

- **Versión:** 1.0.0
- **Lenguaje:** Python ≥ 3.11
- **Framework web:** FastAPI (uvicorn)
- **Base de datos:** SQLite (WAL) → [[Modelo de Datos]]
- **Frontend:** plantillas Jinja2 + JS vanilla, empaquetado por `scripts/build.py`
- **Repo:** `/home/abddallah/AnyOne`

---

## Mapa de documentación

### Visión general
- [[Arquitectura]] — flujo de la aplicación, procesos y concurrencia
- [[Estructura del Proyecto]] — árbol de directorios y responsabilidades
- [[Configuración]] — variables de entorno y opciones
- [[Instalación y Despliegue]] — arranque local y con Docker
- [[Desarrollo]] — linting, tipado, tests y build del frontend

### Datos
- [[Modelo de Datos]] — esquema SQLite y migraciones

### API (prefijo `/api`)
- [[API]] — índice, convenciones y códigos de error
- [[API - Búsqueda y Contenido]]
- [[API - Descargas y Cola]]
- [[API - Biblioteca y Progreso]]
- [[API - Media y Streaming]]
- [[API - Configuración de Fuentes]]
- [[API - Actualizaciones y Vistos]]

### Fuentes de contenido
- [[Fuentes]] — índice de fuentes y mecanismo de descubrimiento
- [[Fuente - JKanime]] — anime (jkanime.net)
- [[Fuente - Ikigai]] — manga (visualikigai)
- [[Fuente - Dinámica]] — scrapers configurables por el usuario

---

## Funcionalidades principales

| Área | Detalle |
|---|---|
| Búsqueda | Por fuente concreta, en todas las fuentes habilitadas, o con streaming SSE por fuente |
| Descargas | Serie completa (con exclusión de capítulos vistos), capítulo único o lote; cola persistida en SQLite con estado en tiempo real |
| Biblioteca | Series descargadas escaneadas del disco, estados (`watching`, `completed`, `pending`, `none`), detección de capítulos nuevos |
| Progreso | Seguimiento por serie y capítulo; recientes (últimos 10) |
| Vistos | Marcar capítulos vistos, borrado por lotes o por capítulo, borrado de series completas |
| Media | Streaming local con soporte de *range requests* (mp4), lector de manga (imágenes), streaming remoto embebido |
| Fuentes dinámicas | Generador de scrapers configurable con detección automática de selectores |

---

## Arranque rápido

```bash
pip install -r requirements.txt
python scripts/build.py
uvicorn app:app --host 0.0.0.0 --port 5000
```

Con Docker:

```bash
docker compose up -d --build
```

Más detalles en [[Instalación y Despliegue]].
