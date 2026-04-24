#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import sys
import cloudscraper
from bs4 import BeautifulSoup

# Configurar logging detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Silenciar logs excesivos de urllib3
logging.getLogger("urllib3").setLevel(logging.WARNING)

def test_cloudscraper_configurations():
    """Prueba diferentes configuraciones de cloudscraper"""
    
    urls = [
        "https://www.zona-leros.com/",
        "https://www.zona-leros.com/search?q=breaking"
    ]
    
    configs = [
        {
            "name": "Configuración por defecto",
            "kwargs": {}
        },
        {
            "name": "Con browser simulation",
            "kwargs": {
                "browser": {
                    "browser": "chrome",
                    "platform": "windows",
                    "desktop": True,
                    "mobile": False
                },
                "delay": 15
            }
        },
        {
            "name": "Con interpreter challenge",
            "kwargs": {
                "interpreter": "js2py",  # o 'nodejs' si tienes Node instalado
                "delay": 15
            }
        }
    ]
    
    for config in configs:
        print("\n" + "="*70)
        print(f"Probando: {config['name']}")
        print("="*70)
        
        try:
            scraper = cloudscraper.create_scraper(**config['kwargs'])
            
            # Headers adicionales para parecer más real
            scraper.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            })
            
            for url in urls:
                print(f"\n--- Solicitando: {url} ---")
                try:
                    resp = scraper.get(url, timeout=30)
                    print(f"Status code: {resp.status_code}")
                    print(f"Final URL: {resp.url}")
                    print("Headers relevantes:")
                    for key in ['server', 'cf-ray', 'cf-cache-status', 'set-cookie']:
                        if key in resp.headers:
                            print(f"  {key}: {resp.headers[key]}")
                    
                    # Verificar si es página de Cloudflare
                    if "Just a moment..." in resp.text:
                        print("⚠️  DETECTADO: Cloudflare challenge (Just a moment...)")
                        # Extraer información del desafío
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        title = soup.find('title')
                        if title:
                            print(f"  Título: {title.get_text()}")
                        # Ver si hay meta refresh
                        meta = soup.find('meta', attrs={'http-equiv': 'refresh'})
                        if meta and meta.get('content'):
                            print(f"  Meta refresh: {meta['content']}")
                    elif "Access denied" in resp.text or "blocked" in resp.text.lower():
                        print("⚠️  DETECTADO: Acceso denegado")
                    else:
                        print("✅ Posiblemente OK (sin página de Cloudflare aparente)")
                        # Mostrar primeros 500 caracteres
                        print("\n--- Primeros 500 caracteres de la respuesta ---")
                        print(resp.text[:500])
                        print("...\n")
                    
                    # Guardar respuesta completa para análisis
                    filename = f"debug_{config['name'].replace(' ', '_')}_{url.split('?')[0].split('/')[-2]}.html"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(resp.text)
                    print(f"Respuesta guardada en: {filename}")
                    
                except Exception as e:
                    print(f"ERROR en {url}: {type(e).__name__}: {e}")
                    
        except Exception as e:
            print(f"Error creando scraper: {e}")

def test_with_custom_session():
    """Prueba con requests.Session personalizada + cloudscraper"""
    print("\n" + "="*70)
    print("Probando con sesión personalizada (cloudscraper + requests.Session)")
    print("="*70)
    
    scraper = cloudscraper.create_scraper()
    # Forzar un User-Agent de Windows/Chrome
    scraper.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    # Primero hacer una petición a la home para obtener cookies iniciales
    try:
        print("Paso 1: Accediendo a la página principal...")
        home = scraper.get("https://www.zona-leros.com/", timeout=30)
        print(f"Home status: {home.status_code}")
        print(f"Cookies recibidas: {scraper.cookies.get_dict()}")
        
        # Verificar si ya tenemos cf_clearance
        if 'cf_clearance' in scraper.cookies:
            print("✅ Cookie cf_clearance presente")
        else:
            print("⚠️ No se encontró cf_clearance")
        
        # Ahora buscar
        print("\nPaso 2: Buscando 'breaking'...")
        search_resp = scraper.get("https://www.zona-leros.com/search?q=breaking", timeout=30)
        print(f"Search status: {search_resp.status_code}")
        
        if "Just a moment..." in search_resp.text:
            print("❌ Cloudflare aún activo en búsqueda")
        else:
            print("✅ Posible éxito en búsqueda")
            print("Primeros 1000 caracteres:")
            print(search_resp.text[:1000])
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Iniciando depuración de zona-leros.com con cloudscraper")
    print("Versión de cloudscraper:", cloudscraper.__version__)
    
    # Probar configuraciones
    test_cloudscraper_configurations()
    
    # Probar con sesión paso a paso
    test_with_custom_session()
    
    print("\nDepuración completada.")