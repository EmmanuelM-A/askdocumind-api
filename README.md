# AskDocuMind API

Upload your documents and ask questions about them. AskDocuMind finds the
relevant passages and answers from them, naming the files it used.

**[Try the live demo](https://askdocumind.com)** ·
**[Browse the API docs](https://api.askdocumind.com/api/docs)**

This repository is the backend API. No sign-up is needed: each visitor gets an
anonymous session that expires after an hour, and their files are then deleted.

## Features

- Upload PDF, Word (`.docx`), text, Markdown, HTML and code files, up to 10 MB
  each and 10 per chat.
- Ask questions in plain language and get answers based only on your files,
  with the names of the files used.
- Optionally search the web when your files don't have the answer.
- Keep up to 5 separate chats, each with its own files.

## How it works

1. **Upload.** The file is stored in S3-compatible storage and processed in
   the background: its text is extracted, split into chunks, and each chunk is
   turned into an embedding (a vector that captures its meaning).
2. **Search.** When you ask a question, it is rewritten into a fuller search
   query, embedded the same way, and compared with your chunks in PostgreSQL
   using pgvector. The best matches can be reranked by a second model.
3. **Answer.** The top chunks, plus web results if you asked for them, are
   given to the language model, which answers from them only.

## Tech stack

- **API:** Python 3.12, FastAPI
- **Database:** PostgreSQL with pgvector, SQLAlchemy and Alembic
- **AI:** OpenAI `gpt-4o-mini` and `text-embedding-3-small` through LangChain,
  with an optional cross-encoder reranker
- **Storage:** S3-compatible object storage (MinIO locally)
- **Web search:** Brave Search
- **Hosting:** Docker on Railway, with a Neon database

## Run it locally

You need Python 3.12, Docker, and an OpenAI API key.

1. Clone the repository and install the dependencies:

   ```bash
   git clone https://github.com/EmmanuelM-A/askdocumind-api.git
   cd askdocumind-api
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Start PostgreSQL and MinIO:

   ```bash
   docker compose up -d
   ```

3. Create the upload bucket. Open the MinIO console at
   <http://localhost:9001>, sign in with `admin` / `secretpassword`, and create
   a bucket called `askdocumind-uploads`.

4. Create your `.env` file and add your OpenAI key to it:

   ```bash
   cp .env.example .env
   ```

5. Create the database tables, then start the API:

   ```bash
   alembic upgrade head
   python -m src.server
   ```

The API runs at <http://localhost:5001>, with interactive docs at
<http://localhost:5001/api/docs>.

The cross-encoder reranker is optional and adds about 450 MB of memory. To use
it, install CPU-only `torch` and then `requirements-reranker.txt`, as the
`Dockerfile` does.

## Configuration

Settings are read from environment variables or `.env`. These are required:

| Variable | What it is |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string, using the `postgresql+asyncpg://` driver |
| `ANONYMOUS_TOKEN_SECRET` | Random string of at least 32 characters that signs session cookies |
| `OPENAI_API_KEY` | OpenAI API key |
| `BRAVE_API_KEY` | Brave Search API key. Any value works if you don't use web search |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Object storage credentials |
| `S3_BUCKET_NAME` | Bucket that stores uploaded files |
| `S3_ENDPOINT_URL` | Object storage URL. Leave unset for AWS S3 |

Everything else has a sensible default. All settings, with their defaults
and limits, are in [`src/config/configs.py`](src/config/configs.py). Common
ones to change are `ENV` (`development` or `production`), `CORS_ORIGINS` (the
frontend URLs allowed to call the API) and `LOG_LEVEL`.

## API overview

All routes are under `/api`. The [API docs](https://api.askdocumind.com/api/docs)
list every request and response.

| Route | What it does |
| --- | --- |
| `POST /v1/auth/anonymous/init` | Start an anonymous session (sets the session cookie) |
| `POST /v1/chat-session/init` | Get your latest chat, or create one |
| `POST /v1/chat-session` | Create a new chat |
| `GET` / `DELETE /v1/chat-session/{id}` | Get or delete a chat |
| `POST /v1/uploads/{chat_id}` | Upload a file to a chat |
| `GET /v1/uploads/{chat_id}` | List a chat's files |
| `POST /v1/chatbot/{chat_id}/ask` | Ask a question about a chat's files |
| `GET /health/server`, `GET /health/db` | Health checks |

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/unit
```

The integration and end-to-end tests also need the Docker services from
step 2 running: `pytest tests/integration tests/e2e`. No test calls OpenAI or
Brave Search, so running them is free.

## Deployment

The API is deployed as a Docker image on Railway.

- **Build:** `docker build .` builds the full image. Add
  `--build-arg WITH_RERANKER=false` for a smaller image without the reranker.
- **Migrate:** run `alembic upgrade head` before each new version takes
  traffic. On Railway, this is the Pre-deploy Command.
- **Health check:** use `/api/health/server`.
- **One instance only.** Background jobs and rate limits are kept in memory,
  so running more than one instance can process the same upload twice.
- **Rolling back:** redeploy the previous deployment. If the bad release ran
  a migration, run `alembic downgrade -1` first.

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE).
