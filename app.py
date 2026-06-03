#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading

from flask import Flask
from flask_cors import CORS

import config
from core.database import init_db, cleanup_download_queue
from core.download_worker import start_workers
from blueprints.main import main_bp
from blueprints.api import api_bp
from core.sources import get_source


def _start_update_scheduler(app):
    """
    Lanza un hilo daemon que dispara la comprobación de actualizaciones
    una vez al día. El primer disparo ocurre 60 segundos después de
    arrancar el servidor (para no solaparse con el inicio).
 
    Usa un app context para poder hacer la petición interna a través
    del test_client, de forma que reutiliza toda la lógica de api.py
    sin duplicarla.
    """
    CHECK_INTERVAL = 24 * 60 * 60   # 24 horas en segundos
    INITIAL_DELAY  = 60              # esperar 1 minuto tras el arranque
 
    def _run():
        import time
        time.sleep(INITIAL_DELAY)
        while True:
            try:
                with app.app_context():
                    with app.test_client() as client:
                        resp = client.post('/api/library/check-all-updates')
                        data = resp.get_json() or {}
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

    def _warm_ikigai_cache() -> None:
        """Precarga el catálogo de Ikigai si no está ya en caché."""
        try:
            source = get_source('anime', 'ikigai')   # ajusta el tipo/nombre si difiere
            if source and hasattr(source, 'warm_cache'):
                source.warm_cache()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"No se pudo precargar catálogo Ikigai: {exc}")


    # Registrar blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

    threading.Thread(target=_warm_ikigai_cache, daemon=True).start()

    return app


if __name__ == '__main__':
    app = create_app()
    print("🔧 Iniciando servidor...")
    print(f"📁 Directorio de descargas: {config.BASE_DOWNLOAD_DIR}")
    print(f"🗄️  Base de datos: {config.DB_PATH}")
    print("🌐 Fuentes cargadas:")
    print("   Anime : jkanime")
    print("   Manga : olympus, nartag, manhwaweb, ikigai")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)