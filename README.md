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

## Environment variables

The backend is configured entirely through environment variables, all prefixed
with `EASYSHARE_`. They can be set via a `backend/.env` file (see
`backend/.env` for a template to copy) when running locally, or passed as
`environment` entries to the `backend` service in `docker-compose.yml` when
running with Docker.

| Variable                                | Default                            | Description                                                                 |
| ---------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| `EASYSHARE_SECRET_KEY`                   | `change-me-in-production-this-is-not-secure` | Secret used to sign JWT access tokens. **Must** be overridden with a long, random value in production (e.g. `openssl rand -hex 32`). |
| `EASYSHARE_ENVIRONMENT`                  | `development`                       | Deployment environment name (e.g. `development`, `production`).             |
| `EASYSHARE_DEBUG`                        | `false`                              | Enables debug mode when set to `true`.                                      |
| `EASYSHARE_ACCESS_TOKEN_EXPIRE_MINUTES`  | `1440`                               | Lifetime of JWT access tokens, in minutes.                                   |
| `EASYSHARE_ALGORITHM`                    | `HS256`                              | JWT signing algorithm.                                                      |
| `EASYSHARE_DATABASE_URL`                 | `sqlite:///./easyshare.db`           | SQLAlchemy database URL. Use a `postgresql+psycopg://...` URL in production. |
| `EASYSHARE_STORAGE_DIR`                  | `./storage`                          | Directory (or mounted volume) where uploaded files are stored.              |
| `EASYSHARE_MAX_FILE_SIZE`                | `104857600` (100 MB)                 | Maximum size, in bytes, allowed for a single uploaded file.                  |
| `EASYSHARE_MAX_FILES_PER_PACKAGE`        | `50`                                  | Maximum number of files allowed in a single package.                        |
| `EASYSHARE_CORS_ORIGINS`                 | `http://localhost:5173`              | Comma-separated list of allowed CORS origins.                               |

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
