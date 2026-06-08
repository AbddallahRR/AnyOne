#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.types import Receive, Scope, Send

import config
from core.database import cleanup_download_queue, init_db
from core.download_worker import start_workers, stop_workers
from core.settings import settings
from core.sources import SOURCES, sync_source_settings
from routers.api import _check_all_updates_core, api_router
from routers.pages import router as pages_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def _start_update_scheduler():
    CHECK_INTERVAL = 24 * 60 * 60
    CACHE_EVICT_INTERVAL = 24 * 60 * 60
    INITIAL_DELAY = 60

    def _run():
        import time

        from core.disk_cache import search_cache
        time.sleep(INITIAL_DELAY)
        last_cache_evict = 0.0
        while True:
            try:
                data = _check_all_updates_core()
                checked = data.get('checked', 0)
                with_updates = data.get('with_updates', 0)
                logger.info(
                    f"[Scheduler] Comprobación diaria: {checked} series revisadas, "
                    f"{with_updates} con episodios nuevos"
                )
            except Exception as exc:
                logger.error(f"[Scheduler] Error en comprobación diaria: {exc}")

            if time.time() - last_cache_evict >= CACHE_EVICT_INTERVAL:
                try:
                    removed = search_cache.evict_expired()
                    if removed:
                        logger.info(
                            f"[Scheduler] Caché limpiada: {removed} entradas expiradas eliminadas"
                        )
                except Exception as exc:
                    logger.warning(f"[Scheduler] Error limpiando caché: {exc}")
                last_cache_evict = time.time()

            time.sleep(CHECK_INTERVAL)

    t = threading.Thread(target=_run, daemon=True, name="update-scheduler")
    t.start()


async def _warm_all_sources():
    tasks = []
    names = []
    for content_type, sources_dict in SOURCES.items():
        for name, source in sources_dict.items():
            if hasattr(source, 'warm_cache'):
                logger.info(f"Precargando catálogo de {name}...")
                tasks.append(asyncio.wait_for(source.warm_cache(), timeout=30))
                names.append(name)

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                logger.warning(f"No se pudo precargar {name}: {res}")
            else:
                logger.info(f"Catálogo de {name} precargado correctamente")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sync_source_settings()
    cleanup_download_queue()
    start_workers()
    _start_update_scheduler()
    asyncio.create_task(_warm_all_sources())
    yield
    logger.info("Apagando workers...")
    stop_workers()


app = FastAPI(
    title='AnyOne',
    version='1.0.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


class CachedStaticFiles(StaticFiles):
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        original_send = send

        async def send_with_cache(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                path = scope.get("path", "")
                if "/dist/" in path:
                    cache_age = 31536000
                    cache_control = b"public, max-age=31536000, immutable"
                elif path.endswith((".woff2", ".ttf", ".woff")):
                    cache_age = 2592000
                    cache_control = b"public, max-age=2592000"
                else:
                    cache_age = 86400
                    cache_control = b"public, max-age=86400"
                headers = list(headers)
                headers.append((b"cache-control", cache_control))
                message["headers"] = headers
            await original_send(message)

        await super().__call__(scope, receive, send_with_cache)


app.mount('/static', CachedStaticFiles(directory='static'), name='static')
app.include_router(pages_router)
app.include_router(api_router)


@app.get('/health')
def health():
    return {'status': 'ok'}


if __name__ == '__main__':
    import uvicorn
    if settings.secret_key == 'insecure-dev-key-change-in-production':
        logger.warning("⚠️  SECRET_KEY insegura por defecto — cámbiala en producción vía variable de entorno SECRET_KEY")
    print("🔧 Iniciando servidor...")
    print(f"📁 Directorio de descargas: {config.BASE_DOWNLOAD_DIR}")
    print(f"🗄️  Base de datos: {config.DB_PATH}")
    print("🌐 Fuentes cargadas:")
    for stype, sources in SOURCES.items():
        print(f"   {stype}: {', '.join(sources.keys())}")
    uvicorn.run('app:app', host=config.HOST, port=config.PORT, reload=config.DEBUG)
