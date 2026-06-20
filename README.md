# AskDocuMind — Backend

## Setup Instructions

### 1. Start a virtual environment

```bash
source .venv/Scripts/activate  # Windows
```

### 2. Start PostgresSQL Database and pgAdmin

```bash
docker-compose up -d
```

### 3. Start the app

```bash
python -m src.api.server
```

## Migrations (Alembic)

This project uses Alembic for migrations (see `alembic.ini` and `alembic/` folder).

**Apply migrations** (on startup or after pulling changes):

```bash
alembic upgrade head
```

> Always run alembic upgrade head before generating new migrations to ensure the database is in sync.

### During Development

#### Generate a new migration after modifying models:

```bash
alembic revision --autogenerate -m "describe your change"
```

#### View migration history:

```bash
alembic current # show current revision(s)
```

```bash
alembic history --verbose # show migration history
```

#### Roll back the last migration:

```bash
alembic downgrade -1 # roll back one version
```

```bash
alembic downgrade base # roll back all migrations
```

Notes about async SQLAlchemy and Alembic:

Alembic works fine with async SQLAlchemy, but your `alembic/env.py` must be configured to use the correct connection 
setup for async engines (many templates in the community show how to run migrations with an async engine by using 
`sqlalchemy.engine.url.make_url` and creating a sync engine for the migration run). 

If you hit issues, check `alembic/env.py` or use a sync connection URL temporarily for migrations.

## Database GUI access using pgAdmin

How to use pgAdmin:

### 1. Start the compose stack (if not already running):

```bash
docker-compose up -d
```

### 2. Open `http://localhost:8080` in your browser and sign in

Using the credentials `PGADMIN_EMAIL` and `PGADMIN_PASSWORD`.

### 3. Add a new Server in the pgAdmin UI with these connection details:

   - Name: ask_docu_mind_local

   - Host: `database`

   - Port: 5432 (or `${DB_PORT}` mapped port)

   - Maintenance DB: ask_docu_mind_postgres

   - Username: `${DB_USER}`

   - Password: `${DB_PASSWORD}`

Notes on host values:

- If you access pgAdmin from your host machine (browser) and pgAdmin runs in a container, `host.docker.internal` will 
resolve to the host machine, and the mapped port `${DB_PORT}` will forward to the Postgres container.

- Alternatively, if you open the pgAdmin web UI that's running in the same Docker network, you can use the Postgres 
service name `database` as the host inside the connection config.

## Testing

### Parameters

- `--cov=src` — measure coverage for the `src/` folder
- `--cov-report=html` — generate an HTML coverage report in `htmlcov/` folder
- `-v` — verbose output
- `-s` — show print statements output
- `-k "expression"` — run tests matching the expression
- `-m "marker"` — run tests with the given marker
- `-x` — stop after first failure

### Run all tests:

```bash
pytest tests/
```

### Run a specific test file:

```bash
pytest tests/test_filename.py
```

### Run a specific test function:

```bash
pytest tests/test_filename.py::test_function_name
```

### Run tests with detailed output:

```bash
pytest -v tests/
```

### Run tests with coverage and generate HTML report:

```bash
pytest --cov=src tests/ --cov-report=html
```
