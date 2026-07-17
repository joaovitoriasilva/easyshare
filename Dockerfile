# Single-image build: the Vue SPA is built here and baked into the backend
# image, which serves both the API and the frontend itself (see
# backend/app/core/static.py) — no separate nginx/frontend container.

# Stage 0: pinned uv (by digest), used only to export a hash-locked
# requirements file from uv.lock so the runtime install is fully reproducible
# and every downloaded artifact is verified against the lock.
FROM ghcr.io/astral-sh/uv:0.11.18@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 AS uv-dist

# Stage 1: build the frontend
FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: resolve production dependencies from the lock into a hash-pinned
# requirements.txt (dev group excluded; the project itself is excluded because
# it is run from source, not installed as a wheel).
FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91 AS requirements
WORKDIR /tmp/backend
COPY --from=uv-dist /uv /uvx /usr/local/bin/
COPY backend/pyproject.toml backend/uv.lock ./
# Optional runtime extras to bake into the image (comma-separated). The default
# keeps the lean single-node image; enable object storage / a shared rate-limit
# store at build time, e.g.:
#   docker build --build-arg EASYSHARE_EXTRAS="s3" .
#   docker build --build-arg EASYSHARE_EXTRAS="s3,redis" .
ARG EASYSHARE_EXTRAS=""
RUN extra_flags=""; \
    for extra in $(echo "$EASYSHARE_EXTRAS" | tr ',' ' '); do \
        extra_flags="$extra_flags --extra $extra"; \
    done; \
    uv export --no-emit-project --no-dev $extra_flags -o requirements.txt

# Stage 3: backend + bundled frontend
FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# libmagic is required by python-magic (a safeuploads dependency).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install exactly the locked dependencies, verifying every downloaded artifact
# against the hashes exported from uv.lock (supply-chain integrity +
# reproducible builds).
COPY --from=requirements /tmp/backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.txt

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
