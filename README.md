> [!NOTE]
> **GitHub Mirror** - If you are viewing this on GitHub, please be aware that this repository is a read-only mirror. Issues, pull requests, and all project activity are tracked on Codeberg: [https://codeberg.org/joaovitoriasilva/easyshare](https://codeberg.org/joaovitoriasilva/easyshare)

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
| Auth      | JWT access tokens, Argon2id password hashing                      |
| Tests     | pytest (backend), Vitest (frontend)                               |
| CI        | Forgejo Actions (lint, type-check, tests, build, dependency audit) |

## Features

- Email + password authentication with JWT sessions.
- Create packages and upload one or many files, with drag-and-drop, progress,
  cancel/retry and resumable chunked uploads for large files.
- Opt-in sharing with a securely generated share id (token).
- Two visibility modes:
  - **Public** — anyone with the link can view and download.
  - **Restricted** — only allow-listed emails can access.
- Recipients can download everything or a selected subset as a zip.
- Owners can pause, resume, reconfigure or disable a share at any time.

## Security by design

- Passwords are hashed with Argon2id (memory-hard, no 72-byte input limit);
  plaintext is never stored or returned.
- Share tokens use `secrets.token_urlsafe` (unguessable).
- Ownership is enforced on every package/file/share operation.
- Restricted shares hide file listings until an authorised email is provided,
  and re-check the email on every download.
- Uploaded files are stored under opaque random names by default (configurable
  via `EASYSHARE_OBFUSCATE_STORAGE_NAMES`); path traversal is prevented on every
  access.
- Input is validated with Pydantic v2; CORS origins are configurable.
- `Strict-Transport-Security` (HSTS) is sent on HTTPS responses by default;
  a background sweep reconciles orphaned storage objects that lost their
  database row (e.g. after a crash mid-upload).
- CI runs `pip-audit` and `npm audit`, and dependencies were checked against
  the GitHub Advisory Database.

## Screenshots

| | |
| --- | --- |
| ![Packages dashboard](screenshots/dashboard.png) Dashboard — packages overview, storage usage and search | ![Package details](screenshots/package.png) Package details — files, sharing settings and share link |
| ![User profile](screenshots/profile.png) Profile — account details, storage usage and password change | ![User management](screenshots/users.png) Admin — user management and storage quotas |

## Repository layout

```
backend/    FastAPI application, models, migrations and tests
frontend/   Vue 3 single-page application and tests
.forgejo/   CI workflows
Dockerfile  Single image: builds the frontend, bundles it into the backend
docker-compose.yml
```

## Quick start (local)

Backend:

```bash
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
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

EasyShare ships as a **single image**: the FastAPI backend serves the built Vue
SPA itself (no separate nginx/frontend container), available at
http://localhost:8080 (`docker-compose.yml`, dev) (`docker-compose.example.yml`, production). The API lives alongside it under
`/api` on the same origin/port.

## Production notes

### Production configuration guard

`docker-compose.example.yml` sets `EASYSHARE_ENVIRONMENT: production`, which
activates a startup guard that refuses to boot with an insecure secret
(placeholder or shorter than 32 characters). The secret is
a required Compose variable, so the stack will not start until you supply one:

```bash
EASYSHARE_SECRET_KEY="$(openssl rand -hex 32)" \
  docker compose -f docker-compose.example.yml up --build
```

### Trusted proxy headers

The container is published directly (no bundled reverse proxy in front of it
anymore). If you put your own reverse proxy (nginx, Traefik, Pangolin, ...) in
front of it for TLS termination, uvicorn only honours its `X-Forwarded-For`
header (so rate limiting and logs see the real client, not the proxy) from the
addresses listed in `EASYSHARE_FORWARDED_ALLOW_IPS` (default `127.0.0.1`),
which the container entrypoint passes to `--forwarded-allow-ips`. Set it to
your reverse proxy's address; leave it at the default if the container is
reachable directly, since trusting `X-Forwarded-For` from an untrusted peer
lets it forge the client IP and bypass IP-based rate limiting.

### Security headers

`app/core/middleware.py::SecurityHeadersMiddleware` sets
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a
`Content-Security-Policy` on every response (this used to live in
`frontend/nginx.conf` before the frontend and backend were merged into one
image). Add `Strict-Transport-Security` (HSTS) there once the site is served
exclusively over HTTPS.

The CSP is strict same-origin by default. Setting `EASYSHARE_CSP_REPORT_URI_FRONTEND`
adds a `report-uri` directive and allows that endpoint's origin in
`connect-src`, so the optional GlitchTip (Sentry-compatible) crash-reporting SDK
bundled in the SPA can send events without being blocked. Pair it with the
frontend's build-time `VITE_GLITCHTIP_DSN` (see `frontend/README.md`), which
points at the same GlitchTip instance; leave both unset to disable crash
reporting entirely.

### Administrators

The **first account to register becomes an administrator**. Admins get a
**Users** page (`/admin/users`) to manage accounts — edit profiles, activate or
deactivate users, and grant or revoke admin rights — plus an **Audit** page
(`/admin/audit`) with the full security log. So nobody else can claim the first
account on a public instance, register immediately after deploying, or deploy
with `EASYSHARE_ALLOW_REGISTRATION=false` and enable it only long enough to
create your account. Admins cannot revoke their own rights or deactivate
themselves, so an instance always keeps at least one administrator.

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
| `EASYSHARE_DEPLOYMENT_PROFILE`           | `local`                              | Deployment topology: `local` (single node, the default) or `distributed` (multiple workers/replicas). `distributed` refuses to start unless `EASYSHARE_RATE_LIMIT_STORAGE_URI` points at a shared store (Redis), so per-process in-memory limits cannot silently under-enforce across the fleet. |
| `EASYSHARE_ACCESS_TOKEN_EXPIRE_MINUTES`  | `1440`                               | Lifetime of JWT access tokens, in minutes.                                   |
| `EASYSHARE_SHARE_ACCESS_TOKEN_EXPIRE_MINUTES` | `30`                          | Lifetime, in minutes, of the token authorising restricted-share downloads.  |
| `EASYSHARE_ALGORITHM`                    | `HS256`                              | JWT signing algorithm.                                                      |
| `EASYSHARE_PASSWORD_HASH_CONCURRENCY`    | _(CPU count, 2–8)_                    | Maximum number of Argon2id password hashes computed at once. Bounds the memory and CPU a burst of logins/registrations can use; extra requests queue briefly. Defaults to the CPU count (at least 2, capped at 8). |
| `EASYSHARE_LOGIN_MAX_FAILED_ATTEMPTS`    | `10`                                 | Consecutive failed logins before an account is temporarily locked (returns `429`), stopping a slow single-account brute force that stays under the per-IP rate limit. The counter lives on the user row (shared across workers/replicas) and resets on a successful login. Set to `0` to disable lockout. |
| `EASYSHARE_LOGIN_LOCKOUT_MINUTES`        | `15`                                 | How long, in minutes, an account stays locked once `EASYSHARE_LOGIN_MAX_FAILED_ATTEMPTS` is reached. |
| `EASYSHARE_ALLOW_REGISTRATION`           | `true`                               | Set to `false` to disable new user sign-ups (`POST /api/auth/register`); existing users can still log in. |
| `EASYSHARE_DATABASE_URL`                 | `sqlite:///./easyshare.db`           | SQLAlchemy database URL. Use a `postgresql+psycopg://...` URL in production (needs the `postgres` build extra / psycopg). |
| `EASYSHARE_DB_POOL_SIZE`                 | `20`                                 | Connection pool size for server databases (PostgreSQL, etc.); ignored for SQLite. |
| `EASYSHARE_DB_MAX_OVERFLOW`              | `20`                                 | Extra connections allowed beyond the pool size under load (server databases only). |
| `EASYSHARE_DB_POOL_TIMEOUT`              | `30`                                 | Seconds a request waits for a free pooled connection before erroring (server databases only). |
| `EASYSHARE_STORAGE_URI`                  | _(empty)_                            | Storage backend selector. Empty (the default) stores uploads on local disk under `EASYSHARE_STORAGE_DIR`. Set `s3://bucket/prefix?region=…&endpoint_url=…` to use S3-compatible object storage (requires the `s3` build extra / boto3); single-file downloads then redirect to a short-lived presigned URL served by the store. |
| `EASYSHARE_STORAGE_DIR`                  | `./storage`                          | Directory (or mounted volume) where uploaded files are stored (local backend). |
| `EASYSHARE_MAX_FILE_SIZE`                | `104857600` (100 MB)                 | Maximum size, in bytes, allowed for a single uploaded file.                  |
| `EASYSHARE_MAX_FILES_PER_PACKAGE`        | `50`                                  | Maximum number of files allowed in a single package.                        |
| `EASYSHARE_MAX_JSON_BODY_SIZE`           | `1048576` (1 MiB)                    | Hard cap on a non-multipart (e.g. JSON) request body, enforced up front so a small API endpoint can never be made to buffer a huge document. |
| `EASYSHARE_CHUNK_SIZE`                   | `8388608` (8 MiB)                    | Chunk size advertised to clients for resumable/chunked uploads.             |
| `EASYSHARE_MAX_CHUNK_SIZE`               | `16777216` (16 MiB)                  | Server-side hard cap on a single chunk upload request (must be >= `EASYSHARE_CHUNK_SIZE`). |
| `EASYSHARE_UPLOAD_SESSION_TTL_HOURS`     | `24`                                 | How long an abandoned resumable-upload session (and its scratch file) survives before the background sweep removes it. |
| `EASYSHARE_UPLOAD_PRUNE_INTERVAL_HOURS`  | `6`                                  | How often, in hours, the abandoned-upload-session sweep runs.                |
| `EASYSHARE_MAX_ARCHIVE_SIZE`             | `5368709120` (5 GiB)                 | Maximum combined size, in bytes, of a zip download; larger selections are rejected with 413. |
| `EASYSHARE_MAX_CONCURRENT_ARCHIVE_BUILDS` | `4`                                | Maximum number of zip archives built at once. Each build holds a worker thread, so extra requests get 503 (retry) instead of stalling the whole service. |
| `EASYSHARE_STORAGE_QUOTA_TOTAL`          | `0`                                  | Instance-wide storage cap, in bytes; uploads that would exceed it are rejected with 413. `0` (the default) disables the check. |
| `EASYSHARE_STORAGE_QUOTA_PER_USER`       | `1073741824` (1 GiB)                 | Storage budget, in bytes, assigned to each user when their account is created (`0` = unlimited). Defaults to 1 GiB so open registration cannot fill the disk without bound. Existing users keep the value snapshotted at creation; changing it later only affects new accounts. Administrators can adjust any user's quota afterwards on the admin users page. |
| `EASYSHARE_OBFUSCATE_STORAGE_NAMES`      | `true`                               | When `true`, stored files get opaque random names on disk. Set to `false` to store them under readable `{package_id}/{file_id}_{filename}` paths instead. The original filename is always kept in the database; only files uploaded after the change are affected. |
| `EASYSHARE_STORAGE_ORPHAN_RETENTION_HOURS` | `24`                              | Age, in hours, before a stored object with no matching database row is treated as an orphan (e.g. from a crash between writing bytes and committing the row) and swept by a background task. `0` disables the sweep. |
| `EASYSHARE_STORAGE_ORPHAN_PRUNE_INTERVAL_HOURS` | `6`                          | How often, in hours, the orphaned-storage sweep runs.                       |
| `EASYSHARE_CORS_ORIGINS`                 | `http://localhost:5173`              | Comma-separated list of allowed CORS origins.                               |
| `EASYSHARE_RATE_LIMIT_ENABLED`           | `true`                               | Set to `false` to disable API rate limiting.                                |
| `EASYSHARE_RATE_LIMIT_STORAGE_URI`       | `memory://`                         | Rate-limit counter store URI. `memory://` (default) is per-process and fine for a single node; use `redis://…` when running multiple workers/replicas (required by `EASYSHARE_DEPLOYMENT_PROFILE=distributed`, needs the `redis` build extra). |
| `EASYSHARE_FORWARDED_ALLOW_IPS`          | `127.0.0.1`                          | Comma-separated reverse-proxy IPs whose `X-Forwarded-For` uvicorn trusts. Read by the Docker entrypoint, so it must be a real environment variable (e.g. set in Compose), not only in `backend/.env`. Use `*` only when the backend port is not publicly reachable. |
| `EASYSHARE_HSTS_ENABLED`                 | `true`                               | Adds a `Strict-Transport-Security` header on responses served over HTTPS (detected from the proxy-forwarded scheme), pinning the origin to TLS. Never emitted over plain HTTP, so local dev is unaffected. |
| `EASYSHARE_HSTS_MAX_AGE`                 | `63072000` (2 years)                 | `max-age` value, in seconds, sent in the HSTS header.                       |
| `EASYSHARE_HSTS_INCLUDE_SUBDOMAINS`      | `true`                               | Adds `includeSubDomains` to the HSTS header, extending the pin to subdomains. |
| `EASYSHARE_HSTS_PRELOAD`                 | `false`                              | Adds `preload` to the HSTS header. Only enable once every subdomain is HTTPS-ready and you intend to submit the domain to browser preload lists. |
| `EASYSHARE_CSP_REPORT_URI_FRONTEND`               | _(empty)_                            | GlitchTip (Sentry-compatible) security-report endpoint. When set, a `report-uri` directive is added to the `Content-Security-Policy` and the endpoint's origin is allowed in `connect-src` so the SPA's crash-reporting SDK isn't blocked. Pair with the frontend `VITE_GLITCHTIP_DSN` build-time variable pointing at the same instance. Empty (the default) disables it. |
| `EASYSHARE_LOG_LEVEL`                    | `INFO`                               | Root log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                       |
| `EASYSHARE_LOG_FORMAT`                   | `console`                            | Log output format: `console` (human-readable) or `json` (structured, for shippers). |
| `EASYSHARE_SLOW_REQUEST_MS`              | `1000`                               | Requests at or above this many milliseconds are logged at `WARNING` with a `slow` marker (so a shipper can alert on latency) instead of the usual `INFO` access line. Set to `0` to disable. |
| `EASYSHARE_AUDIT_RETENTION_DAYS`         | `30`                                 | Number of days audit-log events are kept; a background task periodically deletes older events. Set to `0` to keep them indefinitely. |
| `EASYSHARE_AUDIT_PRUNE_INTERVAL_HOURS`   | `24`                                 | How often, in hours, the audit-log retention task runs (only when `EASYSHARE_AUDIT_RETENTION_DAYS` is greater than `0`). |
| `EASYSHARE_COUNTER_FLUSH_INTERVAL_SECONDS` | `5`                                | How often, in seconds, a background task flushes in-memory share view/download counters and buffered share-download audit events to the database (coalesces many hot-path updates into one write). `0` disables the flusher. |
| `EASYSHARE_SMTP_HOST`                    | _(empty)_                            | SMTP server host for outgoing mail. When set, unlocking a **restricted** share requires a one-time code emailed to the recipient (proving they control the address, not merely know it). Left empty (the default), email verification is disabled and restricted shares accept any allow-listed address; the UI warns owners when they enable a restricted share in this mode. |
| `EASYSHARE_SMTP_PORT`                    | `587`                                | SMTP server port.                                                           |
| `EASYSHARE_SMTP_USERNAME`               | _(empty)_                            | SMTP username (login). Leave empty for an unauthenticated relay.            |
| `EASYSHARE_SMTP_PASSWORD`               | _(empty)_                            | SMTP password. Provide via a secret, never commit it.                       |
| `EASYSHARE_SMTP_FROM`                   | _(empty)_                            | From/envelope address for verification emails. Falls back to `EASYSHARE_SMTP_USERNAME` when unset. |
| `EASYSHARE_SMTP_USE_TLS`                | `true`                               | Use STARTTLS when connecting to the SMTP server.                            |
| `EASYSHARE_SMTP_TIMEOUT`                | `10`                                 | SMTP socket timeout in seconds (bounds how long a send can hold a worker).  |
| `EASYSHARE_SHARE_VERIFICATION_CODE_TTL_MINUTES` | `10`                          | How long an emailed share-verification code stays valid.                    |
| `EASYSHARE_SHARE_VERIFICATION_MAX_ATTEMPTS`     | `5`                           | Wrong-guess budget before a verification code is invalidated (brute-force bound). |

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

The frontend has a single optional build-time variable, `VITE_GLITCHTIP_DSN`,
which enables GlitchTip crash reporting. Vite inlines it into the SPA bundle
when the frontend is compiled, so — unlike the backend `EASYSHARE_*` settings —
it **cannot** be set at container run time from the entrypoint; pass it to the
image build instead, e.g. `docker build --build-arg
VITE_GLITCHTIP_DSN="https://<key>@host/<project>" .` (the `Dockerfile` forwards
it to the frontend build stage; see `frontend/README.md`). Left unset, the
crash SDK is omitted from the bundle entirely. In development, `npm run dev`
(Vite) proxies `/api` requests to `http://localhost:8000` (see
`frontend/vite.config.ts`). In the Docker image the frontend is built into
static files and served by the FastAPI backend itself, on the same origin as
`/api`, so no proxying is needed there at all.

## Scaling to multiple replicas

The default configuration is a self-contained single node: uploads live on
local disk, the database is a SQLite file, and rate-limit counters live in
process memory — no extra services required. Running more than one replica needs
state shared across processes, so switch three backends and declare the topology:

- **Shared database.** SQLite is single-writer and file-local, so point
  `EASYSHARE_DATABASE_URL` at a server database, e.g.
  `postgresql+psycopg://user:pass@host/easyshare` (the PostgreSQL driver ships in
  the `postgres` extra). Like the rate-limit store, the `distributed` profile
  refuses to start while this is left on SQLite.
- **Shared rate-limit store.** Point `EASYSHARE_RATE_LIMIT_STORAGE_URI` at Redis
  (e.g. `redis://redis:6379/0`) so limits are enforced across the fleet rather
  than per-process. Set `EASYSHARE_DEPLOYMENT_PROFILE=distributed`; the app then
  refuses to start on the in-memory store, turning a silent misconfiguration
  into a clear boot error.
- **Shared storage.** Either mount the same network volume at
  `EASYSHARE_STORAGE_DIR` on every replica, or set
  `EASYSHARE_STORAGE_URI=s3://bucket/prefix?region=…&endpoint_url=…` to use
  S3-compatible object storage (MinIO, R2, Ceph, …). With S3, single-file
  downloads redirect to a short-lived presigned URL, so file bytes are served by
  the object store instead of being proxied through the app.
- **Bake in the optional dependencies.** The Postgres, Redis and S3 drivers ship
  only when requested, so build the image with the extras you need:
  `docker build --build-arg EASYSHARE_EXTRAS="postgres,redis,s3" .`

`docker-compose.distributed.example.yml` is a complete, runnable version of the
above: a Traefik load balancer in front of three replicas, backed by PostgreSQL,
Redis and a one-shot migration job.

Two caveats when using S3: the presigned redirect means authenticated
owner-side downloads (issued with `fetch`) require the bucket's CORS policy to
allow the app origin — public share downloads use a normal link and are
unaffected. Also run database migrations once as a separate step rather than
letting every replica run them on start-up (the example's `migrate` service does
exactly this).

## Testing & quality

```bash
# Backend
cd backend && ruff check app tests && mypy app && pytest

# Frontend
cd frontend && npm run lint && npm run type-check && npm run test && npm run build
```

## API overview

Interactive API docs are available at `/docs` when the backend is running.

## License

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcomed! Please open an issue to discuss any changes or improvements before submitting a PR. Check out the [Contributing Guidelines](CONTRIBUTING.md) for more details.
