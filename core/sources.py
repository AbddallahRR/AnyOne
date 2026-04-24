#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Importar todas las fuentes
from sources.jkanime import JkanimeSource
from sources.olympus import OlympusSource
from sources.nartag import NartagSource
from sources.manhwaweb import ManhwawebSource
from sources.ikigai import IkigaiSource

# Registro de fuentes
SOURCES = {
    'anime': {
        'jkanime': JkanimeSource()
    },
    'manga': {
        'olympus': OlympusSource(),
        'nartag': NartagSource(),
        'manhwaweb': ManhwawebSource(),
        'ikigai': IkigaiSource()
    }
}

def get_source(content_type, source_name):
    """Devuelve la instancia de la fuente o None si no existe."""
    return SOURCES.get(content_type, {}).get(source_name)