# EasyShare Backend

Secure file & package sharing API built with **FastAPI**, **Pydantic v2**,
**SQLAlchemy 2** and **Alembic**.

## Features

- User registration & login with JWT access tokens (bcrypt-hashed passwords).
- Packages containing one or more files (upload / download / delete).
- Opt-in sharing: a package is only reachable once the owner enables sharing,
  which mints a cryptographically-random share token.
- Two visibility modes:
  - **public** – anyone with the link can view and download.
  - **restricted** – only recipients whose email is on the allow-list can access.
- Recipients can download all files, or select a subset, as a zip archive.

## Getting started

```bash
cd backend
# Install the locked dependencies (including dev tooling) into .venv
uv sync

# Configure the environment (a secret key is required in production)
cp .env.example .env

# Create the database schema
uv run alembic upgrade head

# Run the API
uv run uvicorn app.main:app --reload
```

Interactive docs are then available at http://localhost:8000/docs.

## Quality gates

```bash
uv run ruff check app tests   # lint
uv run mypy app               # static type checking
uv run pytest                 # tests
```

## Project layout

```
app/
  core/       configuration & security helpers
  db/         engine and session management
  models/     SQLAlchemy ORM models
  schemas/    Pydantic v2 request/response models
  services/   file storage service
  api/        route handlers and dependencies
alembic/      database migrations
tests/        pytest suite
```
