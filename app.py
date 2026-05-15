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


def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.from_object(config)
    CORS(app)  # Restringir origins en producción

    # Inicializar base de datos y limpiar cola
    init_db()
    cleanup_download_queue()

    # Iniciar workers de descarga
    start_workers()

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