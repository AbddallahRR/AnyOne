import os
import re
import json
import sqlite3
import unicodedata
from pathlib import Path
from urllib.parse import quote
from config import ANIME_DOWNLOAD_DIR, MANGA_DOWNLOAD_DIR, DB_PATH

def normalize_title(raw_title):
    """Limpia títulos para usarlos como nombre de carpeta."""
    title = unicodedata.normalize('NFKD', raw_title).encode('ASCII', 'ignore').decode('ASCII')
    title = re.sub(r'[\\/*?:"<>|.,;=+[\]{}()&$#!`~]', '_', title)
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.replace(' ', '_')
    if len(title) > 100:
        title = title[:100].rstrip('_')
    return title

def _normalize_path_name(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = re.sub(r'[-\s_?¿!¡]+', ' ', text)
    return text.strip()

def normalize_for_comparison(text):
    """Normaliza texto para comparación (sin tildes, minúsculas, solo alfanuméricos)."""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def scan_downloaded_series():
    series = []
    
    # Escanear Anime
    anime_dir = Path(ANIME_DOWNLOAD_DIR)
    if anime_dir.exists():
        for serie_dir in anime_dir.iterdir():
            if not serie_dir.is_dir():
                continue
            mp4_files = list(serie_dir.glob("*.mp4"))
            if not mp4_files:
                continue  # Si no hay videos, no añadir la serie
            chapters = []
            for f in mp4_files:
                match = re.search(r'_(\d+)\.mp4$', f.name)
                if match:
                    chapters.append(int(match.group(1)))
            last_chapter = max(chapters) if chapters else 0
            
            # Portada
            cover_url = ''
            info_path = serie_dir / 'series_info.json'
            if info_path.exists():
                try:
                    with open(info_path, 'r') as f:
                        info = json.load(f)
                        cover_filename = info.get('cover', '')
                        if cover_filename:
                            encoded_name = quote(serie_dir.name)
                            cover_url = f"/api/local-cover/anime/{encoded_name}/{cover_filename}"
                except Exception as e:
                    print(f"Error leyendo {info_path}: {e}")
            if not cover_url:
                for ext in ['jpg', 'jpeg', 'png', 'webp']:
                    cover_file = serie_dir / f'cover.{ext}'
                    if cover_file.exists():
                        encoded_name = quote(serie_dir.name)
                        cover_url = f"/api/local-cover/anime/{encoded_name}/cover.{ext}"
                        break
            
            series.append({
                'type': 'anime',
                'id': serie_dir.name,
                'title': serie_dir.name.replace('_', ' ').title(),
                'cover': cover_url,
                'last_chapter': str(last_chapter),
                'progress': '0'
            })
    
    # Escanear Manga
    manga_dir = Path(MANGA_DOWNLOAD_DIR)
    if manga_dir.exists():
        for serie_dir in manga_dir.iterdir():
            if not serie_dir.is_dir():
                continue
            cap_dirs = [d for d in serie_dir.iterdir() if d.is_dir() and d.name.startswith('cap_')]
            if not cap_dirs:
                continue  # Si no hay capítulos, no añadir
            chapters = []
            for d in cap_dirs:
                match = re.search(r'cap_(\d+)', d.name)
                if match:
                    chapters.append(int(match.group(1)))
            last_chapter = max(chapters) if chapters else 0
            
            cover_url = ''
            info_path = serie_dir / 'series_info.json'
            if info_path.exists():
                try:
                    with open(info_path, 'r') as f:
                        info = json.load(f)
                        cover_filename = info.get('cover', '')
                        if cover_filename:
                            encoded_name = quote(serie_dir.name)
                            cover_url = f"/api/local-cover/manga/{encoded_name}/{cover_filename}"
                except Exception as e:
                    print(f"Error leyendo {info_path}: {e}")
            if not cover_url:
                for ext in ['jpg', 'jpeg', 'png', 'webp']:
                    cover_file = serie_dir / f'cover.{ext}'
                    if cover_file.exists():
                        encoded_name = quote(serie_dir.name)
                        cover_url = f"/api/local-cover/manga/{encoded_name}/cover.{ext}"
                        break
            
            series.append({
                'type': 'manga',
                'id': serie_dir.name,
                'title': serie_dir.name.replace('_', ' ').title(),
                'cover': cover_url,
                'last_chapter': str(last_chapter),
                'progress': '0'
            })
    
    # Enriquecer con BD (progreso y portada)
        with sqlite3.connect(DB_PATH) as conn:
            for s in series:
                ref = f"local:{s['id']}"
                # Progreso del usuario
                cur = conn.execute('SELECT chapter, progress FROM user_progress WHERE content_id = ?', (ref,))
                row = cur.fetchone()
                if row and row[0]:
                    s['last_chapter'] = row[0]
                    s['progress'] = row[1]
                else:
                    # No hay progreso: usar capítulo 1 (no el último descargado)
                    s['last_chapter'] = '1'
                    s['progress'] = '0'
                # Portada desde BD (si existe y no se encontró local)
                cur2 = conn.execute('SELECT cover FROM content WHERE id = ?', (ref,))
                row2 = cur2.fetchone()
                if row2 and row2[0] and not s['cover']:
                    s['cover'] = row2[0]
    return series