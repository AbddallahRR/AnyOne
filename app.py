#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import datetime
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.types import Receive, Scope, Send

from core.database import cleanup_download_queue, init_db
from core.download_worker import start_workers, stop_workers
from core.settings import settings
from core.sources import SOURCES, sync_source_settings
from core.updates import check_series
from routers.api import api_router
from routers.pages import router as pages_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def _start_update_scheduler():
    INITIAL_DELAY = 60
    CHECK_INTERVAL = 300       # 5 minutes between ticks
    START_HOUR = 8
    RETRY_INTERVAL = 1800      # 30 minutes between retries
    MAX_RETRIES = 8

    def _run():
        time.sleep(INITIAL_DELAY)
        from core.disk_cache import search_cache
        last_cache_evict = 0.0
        today = None
        # content_ref -> {'attempts': int, 'last_retry': float}
        retry_state: dict = {}
        done_today: set = set()

        while True:
            now = datetime.datetime.now()
            weekday = now.weekday()
            current_date = now.date()

            # Reset state at midnight
            if today != current_date:
                today = current_date
                retry_state.clear()
                done_today.clear()

            # Only run after START_HOUR
            if now.hour < START_HOUR:
                time.sleep(CHECK_INTERVAL)
                continue

            # ── Check scheduled series ──────────────────────────────────
            try:
                from core.db.schedule import get_schedules_for_day
                scheduled = get_schedules_for_day(weekday)

                # Filter series that are due for a check
                due = []
                for s in scheduled:
                    ref = s['content_ref']
                    if ref in done_today:
                        continue

                    state = retry_state.get(ref)
                    if state is None:
                        # First check of the day
                        due.append(s)
                    elif time.time() - state['last_retry'] >= RETRY_INTERVAL:
                        if state['attempts'] >= MAX_RETRIES:
                            logger.info(
                                f"[Scheduler] {ref}: agotados {MAX_RETRIES} reintentos, se deja de intentar hoy"
                            )
                            done_today.add(ref)
                            retry_state.pop(ref, None)
                        else:
                            due.append(s)

                if due:
                    logger.info(
                        f"[Scheduler] {len(due)} serie(s) para checkear hoy a las {now.strftime('%H:%M')}"
                    )
                    for s in due:
                        ref = s['content_ref']
                        try:
                            result = check_series(ref)
                            if result.get('new_chapters'):
                                logger.info(
                                    f"[Scheduler] {ref}: {len(result['new_chapters'])} cap(s) nuevos"
                                )
                                done_today.add(ref)
                                retry_state.pop(ref, None)
                            else:
                                state = retry_state.get(ref)
                                if state is None:
                                    retry_state[ref] = {'attempts': 1, 'last_retry': time.time()}
                                    logger.info(f"[Scheduler] {ref}: sin novedades, comenzando reintentos")
                                else:
                                    state['attempts'] += 1
                                    state['last_retry'] = time.time()
                                    logger.info(
                                        f"[Scheduler] {ref}: sin novedades, reintento {state['attempts']}/{MAX_RETRIES}"
                                    )
                        except Exception as exc:
                            logger.exception(f"[Scheduler] Error chequeando {ref}: {exc}")
            except Exception as exc:
                logger.exception(f"[Scheduler] Error en ciclo de horario: {exc}")

            # ── Cache eviction (unchanged) ──────────────────────────────
            if time.time() - last_cache_evict >= 86400:
                try:
                    removed = search_cache.evict_expired()
                    if removed:
                        logger.info(f"[Scheduler] Caché limpiada: {removed} entradas expiradas")
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
                tasks.append(source.warm_cache())
                names.append(name)

    if tasks:
        sem = asyncio.Semaphore(2)

        async def _warm_one(coro, name):
            async with sem:
                try:
                    await coro
                except Exception as exc:
                    logger.warning(f"No se pudo precargar {name}: {exc}")
                else:
                    logger.info(f"Catálogo de {name} precargado correctamente")

        await asyncio.gather(*[_warm_one(c, n) for c, n in zip(tasks, names)])


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key == 'insecure-dev-key-change-in-production':
        logger.warning("SECRET_KEY insegura por defecto — cámbiala en producción vía variable de entorno SECRET_KEY")
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
    allow_origins=settings.cors_origin_list,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


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
                    cache_control = b"public, max-age=31536000, immutable"
                elif path.endswith((".woff2", ".ttf", ".woff")):
                    cache_control = b"public, max-age=2592000"
                else:
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
    print("🔧 Iniciando servidor...")
    print(f"📁 Directorio de descargas: {settings.base_download_dir}")
    print(f"🗄️  Base de datos: {settings.db_path}")
    print("🌐 Fuentes cargadas:")
    for stype, sources in SOURCES.items():
        print(f"   {stype}: {', '.join(sources.keys())}")
    uvicorn.run('app:app', host=settings.host, port=settings.port, reload=settings.debug,
                backlog=1024, timeout_keep_alive=30)