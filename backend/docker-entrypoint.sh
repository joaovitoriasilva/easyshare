#!/bin/sh
set -e

# Reverse-proxy addresses whose X-Forwarded-For header uvicorn is allowed to
# trust. Defaults to localhost so a spoofed X-Forwarded-For from a directly
# connected client cannot be used to forge the source IP (which would otherwise
# bypass IP-based rate limiting). Set EASYSHARE_FORWARDED_ALLOW_IPS to your
# proxy's address in production, or to "*" only when the backend port is not
# publicly reachable (e.g. it is served solely through the frontend proxy on an
# internal network).
FORWARDED_ALLOW_IPS="${EASYSHARE_FORWARDED_ALLOW_IPS:-127.0.0.1}"

# Apply database migrations before serving traffic.
alembic upgrade head

# exec replaces the shell with uvicorn so it receives signals (SIGTERM) directly
# for a clean shutdown. Quoting "$FORWARDED_ALLOW_IPS" stops the shell from
# glob-expanding a "*" value.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --proxy-headers \
    --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
