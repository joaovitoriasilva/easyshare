# Single-image build: the Vue SPA is built here and baked into the backend
# image, which serves both the API and the frontend itself (see
# backend/app/core/static.py) — no separate nginx/frontend container.

# Stage 1: build the frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: backend + bundled frontend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# libmagic is required by python-magic (a safeuploads dependency).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY backend/ ./
RUN chmod +x docker-entrypoint.sh

# Built frontend assets, served directly by FastAPI at app.core.static's
# default settings.frontend_dir (/app/frontend/dist).
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Run as a dedicated, unprivileged user instead of root. /data is where
# EASYSHARE_DATABASE_URL (sqlite file) and EASYSHARE_STORAGE_DIR (uploads) live
# (see docker-compose*.yml); creating and chown'ing it here means the named
# volume inherits this ownership the first time Docker populates it from the
# image, so the app can still create/write files there at runtime.
RUN groupadd --system easyshare \
    && useradd --system --gid easyshare --no-create-home --shell /usr/sbin/nologin easyshare \
    && mkdir -p /data/storage \
    && chown -R easyshare:easyshare /app /data
USER easyshare

EXPOSE 8080

# Uses the stdlib (no curl/wget in python:slim) to hit the readiness probe,
# which checks the database is actually reachable, not just that the process
# is up.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=2)" || exit 1

# The entrypoint applies migrations then launches uvicorn. Which proxy IPs are
# trusted for X-Forwarded-For is controlled by EASYSHARE_FORWARDED_ALLOW_IPS
# (default 127.0.0.1), so a directly-reachable container cannot be tricked into
# trusting a spoofed client IP.
ENTRYPOINT ["./docker-entrypoint.sh"]
