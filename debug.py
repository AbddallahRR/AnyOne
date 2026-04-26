#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.ikigai import IkigaiSource
from core.disk_cache import search_cache
from core.utils import normalize_title

# Configurar logging para ver detalles
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %message)s')
logger = logging.getLogger(__name__)

def debug_ikigai():
    # Limpiar caché para forzar recarga del catálogo
    print("Limpiando caché de Ikigai...")
    search_cache.delete("ikigai:catalog")
    
    source = IkigaiSource()
    
    # 1. Probar búsqueda
    query = "chupete"
    print(f"\n--- Búsqueda: {query} ---")
    results = source.search(query)
    print(f"Encontrados {len(results)} resultados")
    for i, res in enumerate(results[:5]):
        print(f"{i+1}. ID: {res['id']} | Título: {res['title']} | Cover: {res['cover'][:60]}...")
    
    if not results:
        print("No hay resultados. Revisar CATALOGO_BASE y selectores.")
        return
    
    # Tomar el primer resultado para depurar detalles
    sample_id = results[0]['id']
    print(f"\n--- Detalles de serie: {sample_id} ---")
    print(f"URL solicitada: {source.BASE_URL}/series/{sample_id}/")
    try:
        details = source.get_details(sample_id)
        print("Detalles obtenidos correctamente:")
        print(f"  Título: {details['title']}")
        print(f"  Portada: {details['cover'][:80]}...")
        print(f"  Sinopsis: {details['synopsis'][:200]}...")
    except Exception as e:
        print(f"ERROR al obtener detalles: {e}")
        # Intentar obtener el HTML manualmente para inspeccionar
        try:
            import requests
            url = f"{source.BASE_URL}/series/{sample_id}/"
            resp = source._fetch_url(url)
            print(f"HTML recibido (primeros 800 caracteres):\n{resp[:800]}")
        except Exception as html_err:
            print(f"No se pudo obtener HTML: {html_err}")
    
    # 3. Probar capítulos
    print(f"\n--- Capítulos de serie: {sample_id} ---")
    try:
        chapters = source.get_chapters(sample_id)
        print(f"Obtenidos {len(chapters)} capítulos")
        for ch in chapters[:5]:
            print(f"  Capítulo {ch['number']} -> ID {ch['id']}")
    except Exception as e:
        print(f"ERROR al obtener capítulos: {e}")

if __name__ == "__main__":
    debug_ikigai()