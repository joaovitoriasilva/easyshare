FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libmagic is required by python-magic (a safeuploads dependency).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# Uses the stdlib (no curl/wget in python:slim) to hit the readiness probe,
# which checks the database is actually reachable, not just that the process
# is up.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=2)" || exit 1

# The entrypoint applies migrations then launches uvicorn. Which proxy IPs are
# trusted for X-Forwarded-For is controlled by EASYSHARE_FORWARDED_ALLOW_IPS
# (default 127.0.0.1), so a directly-reachable backend cannot be tricked into
# trusting a spoofed client IP.
ENTRYPOINT ["./docker-entrypoint.sh"]
