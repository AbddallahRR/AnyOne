#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from core.database import get_enabled_source_names

logger = logging.getLogger(__name__)

SOURCES: dict[str, dict[str, object]] = {}
ALL_SOURCES_META: list[dict] = []


def _discover_sources():
    import sources as sources_pkg

    for importer, modname, ispkg in pkgutil.iter_modules(sources_pkg.__path__):
        if modname == '__init__':
            continue

        try:
            module = importlib.import_module(f'sources.{modname}')
        except Exception as exc:
            logger.warning(f'Error importando sources.{modname}: {exc}')
            continue

        source_file = Path(module.__file__) if module.__file__ else None
        if source_file and source_file.exists():
            content = source_file.read_text(encoding='utf-8')
            if '--- IGNORE ---' in content:
                logger.info(f'Fuente ignorada: sources.{modname} (marcada como IGNORE)')
                continue

        from sources import BaseSource

        for name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, BaseSource) and cls is not BaseSource:
                try:
                    instance = cls()
                    source_type = instance.type or ''
                    source_label = instance.label or name
                    if not source_type:
                        logger.warning(f'Fuente {name} no tiene atributo type, omitiendo')
                        continue
                    src_name = name.lower().replace('source', '')
                    SOURCES.setdefault(source_type, {})[src_name] = instance
                    ALL_SOURCES_META.append({
                        'name': src_name,
                        'type': source_type,
                        'label': source_label,
                    })
                    logger.info(f'Fuente auto-descubierta: {src_name} ({source_type})')
                except Exception as exc:
                    logger.warning(f'Error instanciando {name}: {exc}')


def register_dynamic_source(name: str) -> bool:
    """Register a single dynamic source by importing its stub module
    and adding it to SOURCES and ALL_SOURCES_META."""
    modname = f"sources.{name}"
    try:
        module = importlib.import_module(modname)
    except Exception as exc:
        logger.warning(f'Could not import dynamic source {modname}: {exc}')
        return False

    from sources import BaseSource

    found = False
    for cls_name, cls in inspect.getmembers(module, inspect.isclass):
        if issubclass(cls, BaseSource) and cls is not BaseSource:
            try:
                instance = cls()
                source_type = instance.type or ''
                source_label = instance.label or cls_name
                if not source_type:
                    logger.warning(f'Dynamic source {cls_name} sin type, omitiendo')
                    continue
                src_name = name
                SOURCES.setdefault(source_type, {})[src_name] = instance
                # Avoid duplicates in meta
                global ALL_SOURCES_META
                ALL_SOURCES_META = [m for m in ALL_SOURCES_META if m['name'] != src_name]
                ALL_SOURCES_META.append({
                    'name': src_name,
                    'type': source_type,
                    'label': source_label,
                })
                # NO escribir a la BD durante import (lock con --reload).
                # ensure_source_in_db se llama desde sync_source_settings en lifespan.
                logger.info(f'Fuente dinámica registrada: {src_name} ({source_type})')
                found = True
            except Exception as exc:
                logger.warning(f'Error instanciando fuente dinámica {cls_name}: {exc}')
    return found


def sync_source_settings():
    from core.database import ensure_source_in_db

    for src in ALL_SOURCES_META:
        try:
            ensure_source_in_db(src['name'], src['type'])
        except Exception:
            logger.warning(f"No se pudo registrar {src['name']} en source_settings")


_discover_sources()

# Load dynamic (user-generated) sources at startup
try:
    from core.scraper_config import load_dynamic_sources
    load_dynamic_sources()
except Exception as exc:
    logger.warning(f'Error loading dynamic sources: {exc}')


def get_source(content_type, source_name):
    """Devuelve la instancia de la fuente o None si no existe."""
    return SOURCES.get(content_type, {}).get(source_name)


def get_enabled_sources(content_type):
    """Devuelve un dict {nombre: instancia} solo con las fuentes habilitadas."""
    enabled = set(get_enabled_source_names())
    return {
        name: src
        for name, src in SOURCES.get(content_type, {}).items()
        if name in enabled
    }


def get_all_sources_meta():
    """Devuelve la lista de metadatos de todas las fuentes descubiertas."""
    return list(ALL_SOURCES_META)
