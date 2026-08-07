---
tags: [anyone, cache, disco]
tema: any
estado: activo
descripcion: Caché en disco con capas L1/L2 y TTL
---

# DiskCache

Clase `DiskCache` en `core/disk_cache.py`. Caché persistente en disco con expiración por TTL y caché L1 en memoria.

## Capas

- **L1:** dict en memoria (máx. 256 entradas) con evicción **LRU**.
- **L2:** JSON en `cache/` con **escritura atómica** (tempfile + `os.replace`, evita JSON corrupto si muere el proceso).

Cada instancia usa un `namespace` que se antepone a la clave antes de hashearla (`md5`) para evitar colisiones.

## API

| Método | Descripción |
|---|---|
| `get(key)` / `set(key, value, ttl=None)` | Lectura/escritura (TTL opcional por llamada) |
| `aget(key)` / `aset(key, value)` | Versiones asíncronas (no bloquean el event loop) |
| `evict_expired()` | Elimina entradas caducadas del disco (lo llama el scheduler cada 24 h) |
| `delete(key)` / `clear()` | Borrado puntual / total |

## Instancias singulares

| Singleton | TTL | Uso |
|---|---|---|
| `search_cache` | 1800 s | Resultados de búsqueda |
| `details_cache` | 3600 s | Detalles de serie |
| `chapters_cache` | 1800 s | Listas de capítulos |

## Notas relacionadas
- [[Arquitectura]]
- [[Fuentes]]
- [[API - Búsqueda y Contenido]]
