<h1 align="center">Merlin Backend Boilerplate</h1>


## Features

* Fully async FastAPI + SQLAlchemy 2.0
* Pydantic v2 models & validation
* Server-side sessions + CSRF via [crudauth](https://pypi.org/project/crudauth/); OAuth (Microsoft only, lookup-only: signs in users whose `microsoft_id` is set, never creates accounts)
* Annotated type aliases for all FastAPI dependencies
* FastCRUD for efficient CRUD & pagination
* Docker Compose for local / prod / nginx-fronted

## Repo Layout

```text
.
├── backend/                # the deployable application
│   ├── src/                # interfaces/, infrastructure/, modules/
│   ├── pyproject.toml
│   └── Dockerfile          # multi-stage: dev / migrate / prod
└── docs/                   # project documentation (zensical)
```

## Quickstart

```bash
git clone <this-repo>
cd fastApiTemplate
uv sync --all-packages --all-extras   # one venv at the root
```

Configure your env:

```bash
cp backend/.env.example backend/.env
```

Bring it up with Docker:

```bash
cd backend
docker compose up --build
# → http://127.0.0.1:8000  (Swagger at /docs)
```

**Without Docker** (Postgres required locally):

```bash
cd backend
uv run alembic upgrade head
uv run python -m scripts.setup_initial_data   # creates the first admin user + default role
uv run fastapi dev src/interfaces/main.py     # API
```

> Full setup, env-var reference, and per-environment deployment guides live in [docs/](docs/).

## Common tasks

```bash
# lint + format
cd backend && uv run ruff check --fix . && uv run ruff format .

# type check
cd backend && uv run mypy src

# run Alembic migrations
cd backend && uv run alembic revision --autogenerate -m "<msg>" && uv run alembic upgrade head

# run tests
cd backend && uv run pytest
```

More examples (superuser creation, roles, admin usage) in [docs/](docs/).

## Reference

This project is based on [`Fastro`](https://github.com/benavlabs/FastAPI-boilerplate), the open-source FastAPI boilerplate by Benav Labs, with changes applied to fit this project's needs.

### Changes from Fastro

* Moved the `.env` lookup from the repo root to `backend/` in the config file
* Removed the `cli/` (`bp`) package and its workspace entry in `pyproject.toml`
* Added coding agent config in its place
* Changed Tier to Role
* Added Microsoft Oauth

## License

[`MIT`](LICENSE.md)
