# ─── WatchVault: single-container image ────────────────────────────────────
# Stage 1: build the React PWA into static assets.
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: python runtime running nginx + gunicorn + mcp + worker via supervisor.
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx supervisor curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

# App code
COPY backend/ ./backend/
COPY plugins/ ./plugins/

# Built frontend → served by nginx
COPY --from=frontend /build/dist /app/web

# Process & proxy config
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/supervisord.conf /etc/supervisor/conf.d/watchvault.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7210 7211
ENV PYTHONPATH=/app/backend
ENTRYPOINT ["/entrypoint.sh"]
