# AskDocuMind API

A Retrieval-Augmented Generation (RAG) chatbot backend that lets users upload documents and ask questions about them. Built with FastAPI, PostgreSQL + pgvector, and OpenAI.

**Live demo:** [askdocumind.com](https://askdocumind.com)

**Frontend code:** [askdocumind-web](https://github.com/EmmanuelM-A/askdocumind-web)

## Project Overview

AskDocuMind allows users to upload PDF, DOCX, TXT, or Markdown files and immediately start asking natural-language questions about their content. The backend handles document ingestion, vector embedding, semantic search, and LLM-powered response generation.

For the purposes of the demo, no user registration is required, activity is fully tracked within an anonymous user session (cookie sessions).

When the document context is insufficient, the system can optionally fall back to a live web search (via Brave Search API) to supplement the answer.

## Features

- **Document upload**: PDF, DOCX, TXT, and Markdown files up to 0.5 MB each
- **RAG pipeline**: Documents are chunked, embedded, and stored as vectors in PostgreSQL via pgvector
- **Semantic search**: Cosine similarity retrieval finds the most relevant chunks for each query
- **LLM responses**: GPT-powered answers grounded in document context, with prompt injection protection
- **Web search fallback**: Optional Brave Search integration supplements answers when documents lack the information
- **Anonymous sessions**: No sign-up required; sessions are cookie-based and automatically cleaned up after TTL expiry
- **Rate limiting**: Per-user request limits on all endpoints via SlowAPI
- **File validation**: MIME type checking, magic byte validation, size limits, and duplicate detection
- **Structured error responses**: Consistent JSON error shape across all endpoints
- **Health endpoints**: API and database health checks for uptime monitoring

## Architecture

### Request flow (chat query)

1. Client sends query + session cookie to `POST /api/chatbot/query`
2. `AnonymousSessionMiddleware` validates cookie and attaches `user_id` to request state
3. `QueryHandler` embeds the query using OpenAI text-embedding-3-small
4. pgvector cosine similarity search retrieves the top-K relevant document chunks
5. Chunks + query are passed to GPT via a structured prompt
6. LLM returns either an answer, `OUT_OF_SCOPE`, or `NEED_WEB_SEARCH`
7. If `NEED_WEB_SEARCH` and web search is enabled: Brave Search fetches results, content is ingested, and the LLM generates a web-grounded answer
8. Response (answer + sources) is returned to the client

## Technology Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| API framework | FastAPI 0.118 | Async REST API |
| Database | PostgreSQL 16 + pgvector | Document storage and vector search |
| ORM | SQLAlchemy 2 (async) | Database models and queries |
| Migrations | Alembic | Schema versioning |
| LLM | OpenAI GPT-3.5-turbo / GPT-4o-mini | Response generation |
| Embeddings | OpenAI text-embedding-3-small | Semantic vector creation |
| LLM orchestration | LangChain | RAG chain construction |
| File parsing | PyMuPDF, python-docx | PDF and DOCX text extraction |
| Web search | Brave Search API | Optional live search fallback |
| HTML parsing | BeautifulSoup4 | Web content extraction |
| Rate limiting | SlowAPI | Per-user request throttling |
| Session auth | JWT (HS256) in HttpOnly cookies | Anonymous user sessions |
| File storage | Local filesystem / AWS S3 | Document file storage |
| Deployment | Docker + Railway | Container hosting |
| Error tracking | Sentry | Production error monitoring |

## Installation Guide

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- An OpenAI API key

### 1. Clone the repository

```bash
git clone https://github.com/EmmanuelM-A/askdocumind-api.git
cd askdocumind-api
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Copy the env examples from `.env.example` into your `.env` file in the project root and fill in the required values:

```bash
cp .env.example .env
```

### 5. Start the database

```bash
docker-compose up -d
```

This starts a PostgreSQL 16 + pgvector container on port 5432.

### 6. Run database migrations

```bash
alembic upgrade head
```

### 7. Start the API

```bash
uvicorn src.main:app --host localhost --port 5000 --reload

# OR Run this
python -m src.api.server
```

The API is now available at `http://localhost:5000`. Interactive docs are at `http://localhost:5000/api/docs`.

## Environment Variables Reference

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `ENV` | Yes | — | `development` or `production` |
| `PORT` | Yes | — | Port the server listens on |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `USER_SESSION_SECRET` | Yes | — | Secret used to sign session JWTs |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_LLM_MODEL_NAME` | Yes | — | GPT model name (e.g. `gpt-3.5-turbo`) |
| `OPENAI_EMBEDDING_MODEL_NAME` | Yes | — | Embedding model name |
| `CORS_ORIGINS` | Yes | — | JSON array of allowed origins |
| `IS_WEB_SEARCH_ENABLED` | No | `false` | Enable Brave Search fallback |
| `BRAVE_SEARCH_API_KEY` | If web search enabled | — | Brave Search API key |
| `MAX_FILE_SIZE_MB` | No | `0.5` | Max size per uploaded file |
| `MAX_DOCUMENTS_PER_CHAT` | No | `10` | Max documents per session |
| `RETRIEVAL_TOP_K` | No | `5` | Number of chunks retrieved per query |
| `SIMILARITY_THRESHOLD` | No | `0.4` | Minimum cosine similarity score |
| `LLM_MAX_OUTPUT_TOKENS` | No | `1024` | Max tokens in LLM response |
| `MAX_WEB_SEARCHES_PER_SESSION` | No | `3` | Web search calls per session |
| `LOG_LEVEL` | No | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_TO` | No | `FILE` | `CONSOLE`, `FILE`, or `BOTH` |
| `SENTRY_DSN` | No | — | Sentry DSN for error tracking |

## Deployment

The backend is deployed on **Railway** with a PostgreSQL database add-on. The frontend is deployed on **Vercel**. DNS and CDN are managed through **Cloudflare**.

### Production environment variables

Set these in your Railway service's environment settings:

```env
ENV=production
DATABASE_URL=<railway-postgres-url>
USER_SESSION_SECRET=<strong-random-secret>
OPENAI_API_KEY=<your-key>
OPENAI_LLM_MODEL_NAME=gpt-4o-mini
OPENAI_EMBEDDING_MODEL_NAME=text-embedding-3-small
CORS_ORIGINS=["https://yourdomain.com","https://www.yourdomain.com"]
ANON_SESSION_COOKIE_SAMESITE=none
ANON_SESSION_COOKIE_DOMAIN=api.yourdomain.com
LOG_TO=CONSOLE
LOG_LEVEL=INFO
SENTRY_DSN=<your-sentry-dsn>
```

### Docker

A `Dockerfile` is included. To build and run manually:

```bash
docker build -t askdocumind-api .
docker run -p 5000:5000 --env-file .env askdocumind-api
```

## Project Structure

```text
docuchat-backend/
├── src/
│   ├── api/
│   │   ├── controllers/        # Request handling and response assembly
│   │   ├── middleware/         # CORS, session auth, rate limit, request size
│   │   ├── routes/             # FastAPI route definitions
│   │   ├── services/           # Business logic (auth, uploads, chat sessions)
│   │   └── utils/              # Cookie manager, response builders, session manager
│   ├── components/
│   │   ├── chatbot/            # RAGChatbot and QueryHandler
│   │   ├── ingestion/          # Document text extraction and chunking
│   │   ├── prompts/            # Prompt template loader
│   │   └── retrieval/          # Embedder, VectorProcessor, WebSearcher
│   ├── config/
│   │   └── configs.py          # All settings via pydantic-settings
│   ├── database/
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   ├── connection.py       # Async engine and session factory
│   │   └── repository/         # Repository pattern (interfaces + SQLAlchemy impl)
│   ├── errors/                 # Custom exception types
│   └── logger/                 # BaseLogger and formatters
├── data/
│   └── prompts/                # YAML prompt templates
├── alembic/                    # Database migration scripts
├── logs/                       # Runtime log files (gitignored)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## API Documentation

Interactive API documentation is available at `/api/docs` when the server is running.

Key endpoint groups:

| Prefix | Description |
| --- | --- |
| `POST /api/auth/anonymous` | Bootstrap an anonymous user session and receive a session cookie |
| `POST /api/sessions/init` | Create or retrieve the current chat session |
| `POST /api/documents/upload` | Upload one or more documents for the session |
| `GET /api/documents` | List documents in the current session |
| `POST /api/chatbot/query` | Submit a query and receive a RAG-generated answer |
| `GET /api/health/api` | API liveness check |
| `GET /api/health/db` | Database connectivity check |

## Known Limitations

- **One chat session per user**: Anonymous sessions support a single active chat. Multi-session support is a post-v1 roadmap item.
- **No persistent accounts**: Sessions are anonymous and expire after 1 hour of inactivity. Uploaded documents are not retained across sessions.
- **File size cap**: Individual files are limited to 0.5 MB and total upload per session is capped at 2 MB. Large documents should be split before uploading.
- **Web search quota**: Brave Search free tier allows 2,000 requests/month. Per-session web search is capped at 3 calls to stay within quota.
- **English-primary prompts**: The system prompt is written in English. The LLM will respond in the user's language, but prompt injection protection rules are English-only.
- **In-memory web search counter**: The per-session web search limit resets on server restart.
