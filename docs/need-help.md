# Information you might need

## Using Alembic

Run all commands from the project root (where `alembic.ini` lives).

### Generate a new migration

Autogenerate a revision from model changes in `src/database/models.py`:

```bash
alembic revision --autogenerate -m "describe the change"
```

Always inspect the generated file in `alembic/versions/` before running it —
autogenerate misses things like renames (it sees them as a drop + add) and
data migrations.

### Create an empty migration (for manual/data migrations)

```bash
alembic revision -m "describe the change"
```

### Apply migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply just the next one
alembic upgrade +1
```

### Roll back migrations

```bash
# Roll back the last migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision_id>

# Roll back everything
alembic downgrade base
```

### Inspect migration state

```bash
# Show the current revision applied to the DB
alembic current

# Show full migration history
alembic history --verbose

# Show pending (not-yet-applied) migrations
alembic history -r current:head
```

### Renaming a column (pattern used in this repo)

```python
def upgrade() -> None:
    op.alter_column("document", "filename", new_column_name="source")

def downgrade() -> None:
    op.alter_column("document", "source", new_column_name="filename")
```

If the column participates in a `UniqueConstraint`, drop and recreate the
constraint around the rename:

```python
def upgrade() -> None:
    op.drop_constraint("uq_document_session_filename", "document", type_="unique")
    op.alter_column("document", "filename", new_column_name="source")
    op.create_unique_constraint("uq_document_session_source", "document", ["session_id", "source"])
```

## Running the app

```bash
# Start Postgres + pgvector
docker-compose up -d

# Apply migrations
alembic upgrade head

# Run the API (either works)
uvicorn src.main:app --host localhost --port 5000 --reload
python -m src.api.server
```

API docs (Swagger UI): `http://localhost:5000/api/docs`

## Running tests

```bash
# Everything
python -m pytest

# By suite
python -m pytest tests/unit -v
python -m pytest tests/integration -v
python -m pytest tests/e2e -v

# A single file / test
python -m pytest tests/e2e/documents/test_upload_documents_endpoint.py -v
python -m pytest tests/e2e/documents/test_upload_documents_endpoint.py::test_upload_returns_201 -v

# Stop on first failure, show print output
python -m pytest -x -s
```

Notes:

- `asyncio_mode = auto` is set in `pytest.ini`, so `async def test_...`
  functions run without needing `@pytest.mark.asyncio` (some existing tests
  still use the decorator explicitly — both work).
- Integration/e2e tests hit the **real** Postgres database from
  `docker-compose.yml` and (for e2e) the real OpenAI API — make sure
  `docker-compose up -d` is running and `.env` has a valid `OPENAI_API_KEY`
  before running them.
- Each e2e test package opens its own independent `DatabaseConnection` in
  `conftest.py` rather than reusing the app's lifespan-bound connection —
  don't "simplify" this by sharing a global connection across test code and
  the app; asyncpg connections are bound to the event loop they were created
  on, and pytest's loop differs from `TestClient`'s internal loop.

## Database access

```bash
# Connect via psql (matches docker-compose defaults)
docker exec -it <postgres_container_name> psql -U ask_docu_mind -d ask_docu_mind_postgres

# Or from the host, if you have psql installed
psql "postgresql://ask_docu_mind:secret@localhost:5432/ask_docu_mind_postgres"
```

Useful psql commands once connected: `\dt` (list tables), `\d document`
(describe a table), `\q` (quit).

## Docker

```bash
# Start just the database
docker-compose up -d

# Stop it (keeps data volume)
docker-compose down

# Stop it and wipe the data volume (fresh DB next start)
docker-compose down -v

# Build and run the full API image
docker build -t askdocumind-api .
docker run -p 5000:5000 --env-file .env askdocumind-api
```

## Environment variables

Copy `.env.example` to `.env` and fill in the required values (`DATABASE_URL`,
`USER_SESSION_SECRET`, `OPENAI_API_KEY`, model names, `CORS_ORIGINS`, etc.).
Most other settings have sane defaults baked into `src/config/configs.py` and
can be left blank in `.env`. See the README's "Environment Variables
Reference" table for the full list of user-facing settings.

## Logs

Controlled by `LOG_TO` (`CONSOLE`, `FILE`, or `BOTH`) and `LOG_LEVEL`
(`DEBUG`/`INFO`/`WARNING`/`ERROR`). File logs are written under `logs/`
(gitignored).

## Troubleshooting

- **`RuntimeError: ... attached to a different loop`** in tests — a test or
  fixture is reusing the app's global `DatabaseConnection` singleton
  (`get_database_connection()`) from test-side code. Open an independent
  `DatabaseConnection()` in the test's own `conftest.py` instead.
- **Every `/api/chat` request 500s** — check `QUERY_EXPANSION_PROMPT_FILEPATH`
  / `RESPONSE_PROMPT_FILEPATH` actually point to files that exist under
  `data/prompts/`; a bad default here breaks `QueryHandler.__init__` for
  every request.
- **`NO_COOKIE_VALUE` / `INVALID_USER_SIGNATURE` on every request** — you're
  missing the session cookie or `USER_SESSION_SECRET` changed between
  requests (invalidates previously issued cookies). Call
  `POST /api/auth/anonymous` first to get a fresh cookie.
- **Alembic autogenerate produces a drop+add instead of a rename** — this is
  expected; Alembic can't detect renames automatically. Hand-edit the
  generated migration to use `op.alter_column(..., new_column_name=...)`
  instead, so existing data is preserved.
