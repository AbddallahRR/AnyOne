#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path

# Directorio base de descargas
BASE_DOWNLOAD_DIR = os.environ.get('BASE_DOWNLOAD_DIR', os.path.expanduser('~/DescargasComics'))
ANIME_DOWNLOAD_DIR = os.path.join(BASE_DOWNLOAD_DIR, 'Anime')
MANGA_DOWNLOAD_DIR = os.path.join(BASE_DOWNLOAD_DIR, 'Manga')

# Crear directorios si no existen
os.makedirs(ANIME_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MANGA_DOWNLOAD_DIR, exist_ok=True)

# Base de datos SQLite
DB_DIR = os.environ.get('DB_DIR', os.path.expanduser('~/.config/comic_web'))
DB_PATH = os.path.join(DB_DIR, 'history.db')
os.makedirs(DB_DIR, exist_ok=True)

# Configuración de Flask
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    import warnings
    warnings.warn("SECRET_KEY no configurado. Usando clave insegura para desarrollo. Configura la variable de entorno SECRET_KEY en producción.")
    SECRET_KEY = 'insecure-dev-key-change-in-production'
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
HOST = '0.0.0.0'
PORT = 5000