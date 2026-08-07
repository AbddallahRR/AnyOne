---
tags: [anyone, fuentes, anime, jkanime]
tema: any
estado: activo
descripcion: Fuente JKanime — anime, streaming y descargas de vídeo
---

# Fuente - JKanime

- **Archivo:** `sources/jkanime.py`
- **Tipo:** `anime`
- **Etiqueta:** `JKanime`
- **Web:** `https://jkanime.net`

Es la fuente más compleja: episodios de vídeo, varios hosts de archivo, variantes **SUB/DUB** y streaming.

## Métodos principales

- `search_sync(query)` — `/buscar/{q}`; parsea tarjetas `.anime__item`, con fallback de portada a CDN (`cdn.jkdesa.com/assets/images/animes/image/{slug}.jpg`) y regex si el HTML cambia.
- `get_details_sync(content_id)` — bloque `.anime_info`: título, sinopsis, portada y `<li>` con tipo/episodios/géneros.
- `get_chapters_sync(content_id)` — extrae `serie_id` de `#guardar-anime[data-anime]`, obtiene **token CSRF** (Laravel) y consulta el endpoint AJAX `/ajax/episodes/{serie_id}/{page}` (GET con Referer, fallback POST con `_token`).
- `download_chapter_sync(...)` — resuelve servidores, prioriza por `_SERVER_PRIORITY` y escribe `cap_NNN.mp4`.
- `get_episode_links(content_id, chapter_id)` — devuelve `EpisodeLinks` separando `stream`/`download` y SUB/DUB.

## Streaming

`supports_streaming = True`. `get_stream_url_sync()` devuelve, en orden de prioridad:

1. Primer **iframe JKPlayer** nativo (patrón `video[N] = "..."`).
2. URL `remote` decodificada (base64) de servidores streamables: `streamwish`, `voe`, `vidhide`, `mixdrop`, `streamtape`, `doodstream`.
3. Cualquier servidor con `remote` decodificable.

## Descarga de vídeo

- `_download_stream()` — `requests.Session` con streaming y reintentos.
- `_download_curl()` — `curl -L -k -C -` (resume), `--fail`, timeout 60 s conexión / 30 min total, cabeceras UA + Referer + Origin. Valida por `content-length` (HEAD), tamaño mínimo 10 KB y **magic bytes MP4** (`ftyp` en offset 4).
- **Resolvers por host:**
  - *Mediafire*: base64-decode de `remote`, extrae `#downloadButton` o `https://download...mp4`.
  - *Mp4upload*: llama a **`yt-dlp -g`** para obtener la URL directa y valida por HEAD.
  - *Genérico* (jkplayers): `https://c1.jkplayers.com/d/{slug}/` siguiendo redirecciones, acepta `.mp4` directo o scrapea `#downloadButton`.

## Detalles de scraping

- **CSRF:** 4 patrones regex (input `_token`, meta `csrf-token`, `var token`, `_token:` JSON).
- **Servidores:** `_parse_servers_from_table()` y `_parse_servers_from_js()` (normaliza comillas simples en `var servers=[...]`).
- **Caché de HTML de episodios:** LRU en memoria (128 entradas, thread-safe).
- Los capítulos son enteros: `Chapter(number=str(i), id=str(i))`.

## Notas relacionadas
- [[Fuentes]]
- [[API - Media y Streaming]]
- [[Estructura del Proyecto]]
