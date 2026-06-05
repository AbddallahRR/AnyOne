#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Importar todas las fuentes
from sources.ikigai import IkigaiSource
from sources.jkanime import JkanimeSource
from sources.manhwaweb import ManhwawebSource
from sources.nartag import NartagSource

# Registro de fuentes
SOURCES = {
    'anime': {
        'jkanime': JkanimeSource()
    },
    'manga': {
        'nartag': NartagSource(),
        'manhwaweb': ManhwawebSource(),
        'ikigai': IkigaiSource()
    }
}

def get_source(content_type, source_name):
    """Devuelve la instancia de la fuente o None si no existe."""
    return SOURCES.get(content_type, {}).get(source_name)
