# EasyShare

EasyShare is a secure file & package sharing application. Authenticated users
create **packages** (one or more files) and choose when to share them. Sharing
is off by default; enabling it mints a cryptographically-random link that can be
**public** or **restricted** to specific email addresses. Recipients open the
link and download all files, or just the ones they select, as a zip archive.

## Stack

| Layer     | Technology                                                        |
| --------- | ----------------------------------------------------------------- |
| Frontend  | TypeScript, Vue 3, Vite, Tailwind CSS, Reka UI, shadcn-vue        |
| Backend   | Python, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic               |
| Auth      | JWT access tokens, bcrypt password hashing                        |
| Tests     | pytest (backend), Vitest (frontend)                               |
| CI        | GitHub Actions (lint, type-check, tests, build, dependency audit) |

## Features

- Email + password authentication with JWT sessions.
- Create packages and upload one or many files.
- Opt-in sharing with a securely generated share id (token).
- Two visibility modes:
  - **Public** — anyone with the link can view and download.
  - **Restricted** — only allow-listed emails can access.
- Recipients can download everything or a selected subset as a zip.
- Owners can pause, resume, reconfigure or disable a share at any time.

## Security by design

- Passwords are hashed with bcrypt; plaintext is never stored or returned.
- Share tokens use `secrets.token_urlsafe` (unguessable).
- Ownership is enforced on every package/file/share operation.
- Restricted shares hide file listings until an authorised email is provided,
  and re-check the email on every download.
- File storage keys are opaque and path-traversal is prevented.
- Input is validated with Pydantic v2; CORS origins are configurable.
- CI runs `npm audit` and dependencies were checked against the GitHub
  Advisory Database.

## Repository layout

```
backend/    FastAPI application, models, migrations and tests
frontend/   Vue 3 single-page application and tests
.github/    CI workflows
docker-compose.yml
```

## Quick start (local)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend (in another terminal):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Quick start (Docker)

```bash
EASYSHARE_SECRET_KEY="$(openssl rand -hex 32)" docker compose up --build
```

The UI is served at http://localhost:8080 and the API at http://localhost:8000.

## Production notes

### Production configuration guard

`docker-compose.example.yml` sets `EASYSHARE_ENVIRONMENT: production`, which
activates a startup guard that refuses to boot with an insecure secret
(placeholder or shorter than 32 characters) or with debug enabled. The secret is
a required Compose variable, so the stack will not start until you supply one:

```bash
EASYSHARE_SECRET_KEY="$(openssl rand -hex 32)" \
  docker compose -f docker-compose.example.yml up --build
```

### Trusted proxy headers

The backend runs behind the nginx proxy and reads the real client IP from the
`X-Forwarded-For` header (so rate limiting and logs see the client, not the
proxy). uvicorn only honours that header from the addresses listed in
`EASYSHARE_FORWARDED_ALLOW_IPS` (default `127.0.0.1`), which the container
entrypoint passes to `--forwarded-allow-ips`.

Because a trusted header can be spoofed by anyone able to reach uvicorn
directly, `docker-compose.example.yml` does **not** publish the backend port —
the frontend container reaches it over the internal compose network — and sets
`EASYSHARE_FORWARDED_ALLOW_IPS: "*"` (safe precisely because the port is not
reachable from outside). If you deliberately publish the backend port, set
`EASYSHARE_FORWARDED_ALLOW_IPS` to your proxy's address instead of `*`.

### Security headers

`frontend/nginx.conf` sets `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy` and a `Content-Security-Policy` on every response. Enable the
commented-out `Strict-Transport-Security` (HSTS) header once the site is served
exclusively over HTTPS.

## Environment variables

The backend is configured entirely through environment variables, all prefixed
with `EASYSHARE_`. They can be set via a `backend/.env` file (see
`backend/.env` for a template to copy) when running locally, or passed as
`environment` entries to the `backend` service in `docker-compose.yml` when
running with Docker.

| Variable                                | Default                            | Description                                                                 |
| ---------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| `EASYSHARE_SECRET_KEY`                   | `change-me-in-production-this-is-not-secure` | Secret used to sign JWT access tokens. **Must** be overridden with a long, random value in production (e.g. `openssl rand -hex 32`). |
| `EASYSHARE_APP_NAME`                     | `EasyShare`                         | Human-readable application name.                                            |
| `EASYSHARE_ENVIRONMENT`                  | `development`                       | Deployment environment name (e.g. `development`, `production`).             |
| `EASYSHARE_DEBUG`                        | `false`                              | Enables debug mode when set to `true`.                                      |
| `EASYSHARE_ACCESS_TOKEN_EXPIRE_MINUTES`  | `1440`                               | Lifetime of JWT access tokens, in minutes.                                   |
| `EASYSHARE_SHARE_ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                          | Lifetime, in minutes, of the token authorising restricted-share downloads.  |
| `EASYSHARE_ALGORITHM`                    | `HS256`                              | JWT signing algorithm.                                                      |
| `EASYSHARE_ALLOW_REGISTRATION`           | `true`                               | Set to `false` to disable new user sign-ups (`POST /api/auth/register`); existing users can still log in. |
| `EASYSHARE_DATABASE_URL`                 | `sqlite:///./easyshare.db`           | SQLAlchemy database URL. Use a `postgresql+psycopg://...` URL in production. |
| `EASYSHARE_STORAGE_DIR`                  | `./storage`                          | Directory (or mounted volume) where uploaded files are stored.              |
| `EASYSHARE_MAX_FILE_SIZE`                | `104857600` (100 MB)                 | Maximum size, in bytes, allowed for a single uploaded file.                  |
| `EASYSHARE_MAX_FILES_PER_PACKAGE`        | `50`                                  | Maximum number of files allowed in a single package.                        |
| `EASYSHARE_MAX_ARCHIVE_SIZE`             | `5368709120` (5 GiB)                 | Maximum combined size, in bytes, of a zip download; larger selections are rejected with 413. |
| `EASYSHARE_CORS_ORIGINS`                 | `http://localhost:5173`              | Comma-separated list of allowed CORS origins.                               |
| `EASYSHARE_RATE_LIMIT_ENABLED`           | `true`                               | Set to `false` to disable API rate limiting.                                |
| `EASYSHARE_RATE_LIMIT_STORAGE_URI`       | `memory://`                         | Rate-limit counter storage backend URI (e.g. `memory://`, `redis://...`).   |
| `EASYSHARE_FORWARDED_ALLOW_IPS`          | `127.0.0.1`                          | Comma-separated reverse-proxy IPs whose `X-Forwarded-For` uvicorn trusts. Read by the Docker entrypoint, so it must be a real environment variable (e.g. set in Compose), not only in `backend/.env`. Use `*` only when the backend port is not publicly reachable. |
| `EASYSHARE_LOG_LEVEL`                    | `INFO`                               | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                       |
| `EASYSHARE_LOG_FORMAT`                   | `console`                            | Log output format: `console` (human-readable) or `json` (structured, for shippers). |

When running locally, edit `backend/.env` directly (it is loaded automatically
by the backend on startup) or export the variables in your shell before
running `uvicorn`.

When running with Docker Compose, set the variables on your shell before
starting the stack, or add them to the `backend.environment` section of
`docker-compose.yml`:

```bash
EASYSHARE_SECRET_KEY="$(openssl rand -hex 32)" \
EASYSHARE_DATABASE_URL="postgresql+psycopg://user:pass@host/db" \
docker compose up --build
```

The frontend has no build-time environment variables: in development it proxies
`/api` requests to `http://localhost:8000` (see `frontend/vite.config.ts`), and
in the Docker image `nginx.conf` proxies `/api` to the `backend` service.

## Testing & quality

```bash
# Backend
cd backend && ruff check app tests && mypy app && pytest

# Frontend
cd frontend && npm run lint && npm run type-check && npm run test && npm run build
```

## API overview

Interactive API docs are available at `/docs` when the backend is running.
