# syntax=docker/dockerfile:1

# Stage 1: compilar dependencias con headers de C
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: imagen final limpia
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias compiladas del builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

RUN mkdir -p /data/descargas/Anime /data/descargas/Manga /data/config

ENV BASE_DOWNLOAD_DIR=/data/descargas
ENV DB_DIR=/data/config

EXPOSE 5000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]