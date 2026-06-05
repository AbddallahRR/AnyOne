#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

import config
from core.database import cleanup_download_queue, init_db
from core.download_worker import start_workers
from core.settings import settings
from core.sources import SOURCES
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


def _warm_all_sources():
    async def _warm():
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
    asyncio.run(_warm())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    cleanup_download_queue()
    start_workers()
    _start_update_scheduler()
    threading.Thread(target=_warm_all_sources, daemon=True).start()
    yield


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

app.mount('/static', StaticFiles(directory='static'), name='static')
app.include_router(pages_router)
app.include_router(api_router)


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
