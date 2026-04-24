# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Dependencias del sistema necesarias para yt-dlp y Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (aprovecha caché de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la app
COPY . .

# Crear directorios internos que usa la app
RUN mkdir -p /data/descargas/Anime /data/descargas/Manga /data/config

# Variables de entorno para sobreescribir config.py
ENV BASE_DOWNLOAD_DIR=/data/descargas
ENV DB_DIR=/data/config
ENV FLASK_ENV=production

EXPOSE 5000

CMD ["python", "app.py"]
