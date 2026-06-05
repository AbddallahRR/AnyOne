#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading

from flask import Flask
from flask_cors import CORS

import config
from core.database import init_db, cleanup_download_queue
from core.sources import SOURCES
from core.download_worker import start_workers
from blueprints.main import main_bp
from blueprints.api import api_bp, _check_all_updates_core


def _start_update_scheduler(app):
    """
    Lanza un hilo daemon que dispara la comprobación de actualizaciones
    una vez al día. El primer disparo ocurre 60 segundos después de
    arrancar el servidor (para no solaparse con el inicio).
 
    También ejecuta la limpieza de caché expirada diariamente.
    """
    CHECK_INTERVAL   = 24 * 60 * 60   # 24 horas en segundos
    CACHE_EVICT_INTERVAL = 24 * 60 * 60  # 24 horas
    INITIAL_DELAY    = 60              # esperar 1 minuto tras el arranque
 
    def _run():
        import time
        from core.disk_cache import search_cache, CACHE_DIR
        time.sleep(INITIAL_DELAY)
        last_cache_evict = 0.0
        while True:
            try:
                data = _check_all_updates_core()
                checked      = data.get('checked', 0)
                with_updates = data.get('with_updates', 0)
                import logging
                logging.getLogger(__name__).info(
                    f"[Scheduler] Comprobación diaria: {checked} series revisadas, "
                    f"{with_updates} con episodios nuevos"
                )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(f"[Scheduler] Error en comprobación diaria: {exc}")

            # Limpieza periódica de caché expirada
            if time.time() - last_cache_evict >= CACHE_EVICT_INTERVAL:
                try:
                    removed = search_cache.evict_expired()
                    if removed:
                        import logging
                        logging.getLogger(__name__).info(
                            f"[Scheduler] Caché limpiada: {removed} entradas expiradas eliminadas"
                        )
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning(f"[Scheduler] Error limpiando caché: {exc}")
                last_cache_evict = time.time()

            time.sleep(CHECK_INTERVAL)
 
    t = threading.Thread(target=_run, daemon=True, name="update-scheduler")
    t.start()


def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.from_object(config)
    CORS(app)  # Restringir origins en producción

    # Inicializar base de datos y limpiar cola
    init_db()
    cleanup_download_queue()

    # Iniciar workers de descarga
    start_workers()

    _start_update_scheduler(app)

    def _warm_all_sources() -> None:
        """Precarga los catálogos de todas las fuentes en background."""
        import logging
        logger = logging.getLogger(__name__)
        for content_type, sources_dict in SOURCES.items():
            for name, source in sources_dict.items():
                if hasattr(source, 'warm_cache'):
                    try:
                        logger.info(f"Precargando catálogo de {name}...")
                        source.warm_cache()
                    except Exception as exc:
                        logger.warning(f"No se pudo precargar {name}: {exc}")


    # Registrar blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

    threading.Thread(target=_warm_all_sources, daemon=True).start()

    return app


if __name__ == '__main__':
    app = create_app()
    print("🔧 Iniciando servidor...")
    print(f"📁 Directorio de descargas: {config.BASE_DOWNLOAD_DIR}")
    print(f"🗄️  Base de datos: {config.DB_PATH}")
    print("🌐 Fuentes cargadas:")
    for stype, sources in SOURCES.items():
        print(f"   {stype}: {', '.join(sources.keys())}")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)