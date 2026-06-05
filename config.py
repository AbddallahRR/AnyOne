#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path

from core.settings import settings

# Directorio base de descargas
BASE_DOWNLOAD_DIR = str(settings.base_download_dir)
ANIME_DOWNLOAD_DIR = str(settings.anime_download_dir)
MANGA_DOWNLOAD_DIR = str(settings.manga_download_dir)

# Crear directorios si no existen
os.makedirs(ANIME_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MANGA_DOWNLOAD_DIR, exist_ok=True)

# Base de datos SQLite
DB_DIR = str(settings.db_dir)
DB_PATH = str(settings.db_path)
os.makedirs(DB_DIR, exist_ok=True)

# Configuración de Flask
SECRET_KEY = settings.secret_key
DEBUG = settings.debug
HOST = settings.host
PORT = settings.port