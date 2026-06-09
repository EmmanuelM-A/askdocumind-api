# Refactor Plan: S3 File Storage First, Then pgvector

This document captures the next infrastructure refactor in two phases:

1. move uploaded file bytes from local disk to AWS S3 while the rest of the app still works,
2. then migrate vector persistence from the current FAISS/local-file setup to PostgreSQL + `pgvector`.

The goal is to keep the current API flow stable while changing only the storage layer first, then the retrieval layer.

---

## Current state summary

The backend currently uses:

- `src/database/storage/local_file_storage_service.py` for file bytes on disk,
- `src/database/storage/storage_service_factory.py` to return the current storage implementation,
- `src/components/retrieval/faiss_store.py` for vector storage on disk,
- `src/components/retrieval/embedder.py` to create embeddings,
- `src/components/chatbot/core.py` to orchestrate upload/query flows,
- `src/api/services/document_uploads.py` to save files, create metadata, and trigger vector processing,
- `src/database/models.py` and Alembic migrations for the database metadata models.

There is already an empty `src/database/storage/s3_storage_service.py` stub, so the storage abstraction already exists and can be swapped cleanly.

---

## Phase 1 — Implement S3 file storage

### Goal

Store uploaded document bytes in S3 instead of the local filesystem, while keeping the rest of the upload/delete workflow unchanged.

### Recommended order

1. Add AWS configuration.
2. Implement `S3StorageService`.
3. Update the storage factory to choose S3 or local storage by environment.
4. Update upload/delete flows to rely on the storage abstraction only.
5. Add tests for S3 behavior using mocks.

### AWS setup checklist

Before coding, create and configure:

- an AWS account,
- an S3 bucket for document uploads,
- an IAM user or role with least-privilege access,
- access keys for local development, or an IAM role for production.

Suggested AWS settings:

- **Bucket name:** something stable and environment-specific, e.g. `docuchat-dev-documents` / `docuchat-prod-documents`.
- **Region:** whichever region you want to deploy in.
- **Bucket versioning:** optional, but useful if you want recovery.
- **Server-side encryption:** enable it.
- **Public access:** keep blocked.

Suggested IAM permissions for the app:

- `s3:PutObject`
- `s3:GetObject`
- `s3:DeleteObject`
- `s3:ListBucket`
- optionally `s3:DeleteObjectTagging` if you later use object tags

### Environment variables to add

Add these to `.env`, Docker, and deployment secrets:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`
- `S3_BUCKET_NAME`
- `S3_PREFIX` or similar, if you want an app-specific prefix inside the bucket
- `STORAGE_BACKEND=s3` for production, `STORAGE_BACKEND=local` for dev if you want toggling

If you want separate environments, also keep:

- `LOCAL_FILE_STORAGE_DIR` for dev fallback,
- a dev S3 bucket name if you want to test S3 locally against real AWS.

### Files likely to change for S3

#### Storage layer

- `src/database/storage/s3_storage_service.py`
- `src/database/storage/storage_service_factory.py`
- `src/database/storage/storage_service.py`
- `src/database/storage/local_file_storage_service.py` if you want both implementations to share helper behavior

#### Config / environment

- `src/config/configs.py`
- `.env`
- `docker-compose.yml`
- deployment environment configuration

#### API/service layer

- `src/api/services/document_uploads.py`
- any delete/cleanup code that currently assumes local file paths

#### Tests

- `tests/unit/...` for storage service behavior
- `tests/integration/storage/...` if you add real S3 integration tests later

### Implementation notes for `S3StorageService`

The service should match the current `StorageService` contract:

- `save(key, data)` → upload bytes to S3,
- `load(key)` → download bytes or return `None`,
- `delete(key)` → remove a single object,
- `exists(key)` → check for object existence,
- `delete_all(prefix)` → delete everything under a prefix.

Important behavior to preserve:

- Use the same key format the app already expects, usually something like `chat_id/filename`.
- Make sure the service is safe for repeated calls.
- Treat `delete_all(chat_id)` as the operation that removes a whole chat folder/prefix.
- Avoid hardcoding local paths in the upload/delete flows.

### S3 folder semantics

S3 does not have real folders. A “folder” is a key prefix.

That means deleting an entire chat folder becomes:

- delete all objects with prefix `chat_id/`.

This is the S3 equivalent of deleting a local directory tree.

### S3 rollout strategy

To reduce risk, deploy in this order:

1. Implement S3 service behind the existing storage interface.
2. Keep local storage available for dev.
3. Switch only production to S3 via config.
4. Verify upload, download, delete, and delete-all behavior.
5. Only after that, move on to pgvector.

---

## Phase 2 — Integrate pgvector

### Goal

Move embeddings into PostgreSQL using `pgvector`, so vector data and document metadata live in the same database rather than in FAISS metadata files.

### What pgvector changes conceptually

Today:

- embeddings live in FAISS index files,
- metadata lives beside the FAISS store,
- retrieval reads vectors from disk.

With pgvector:

- embeddings are stored in a PostgreSQL table column of type `vector`,
- metadata lives in normal relational columns or JSONB,
- similarity search becomes a SQL query using vector distance operators.

### Recommended database design

Create a dedicated table for embeddings/chunks instead of forcing everything into the current `document` table.

A good shape is:

- `id`
- `document_id`
- `session_id`
- `chunk_index`
- `chunk_text`
- `chunk_metadata` as JSONB
- `embedding` as `vector(n)`
- timestamps

Why this is better:

- one document can have many chunks,
- each chunk can have its own embedding,
- searches can return chunk-level matches,
- metadata and embeddings stay in one DB,
- cleanup becomes easier because deleting a document or chat can cascade through a relational model.

### pgvector setup checklist

1. Install the pgvector extension in PostgreSQL.
2. Add a table/column using the `vector` type.
3. Create indexes for similarity search.
4. Update the repository layer to persist and query embeddings.
5. Refactor retrieval to query PostgreSQL instead of FAISS files.

### Files likely to change for pgvector

#### Database / model layer

- `src/database/models.py`
- `alembic/env.py`
- `alembic/versions/*.py`
- possibly new model files if you split the schema later

#### Repository layer

- `src/database/repository/interfaces/`
- `src/database/repository/sqlalchemy/`

#### Retrieval layer

- `src/components/retrieval/vector_store.py`
- `src/components/retrieval/faiss_store.py`
- likely a new PostgreSQL-backed vector store implementation

#### Chat / upload flow

- `src/components/chatbot/core.py`
- `src/api/services/document_uploads.py`
- any query handler code that assumes a FAISS index object is returned

#### Config / dependencies

- `requirements.txt`
- `src/config/configs.py`
- `docker-compose.yml`

### Dependency changes you will likely need

Add packages for:

- PostgreSQL vector support (`pgvector` Python package or equivalent integration)
- PostgreSQL driver support if needed for your current environment
- AWS SDK for S3 (`boto3` or similar)

Your current `requirements.txt` already includes SQLAlchemy and async support patterns, but it does not currently include AWS or pgvector-specific packages.

### Migration strategy for pgvector

Do not try to move every search path at once.

Recommended sequence:

1. Add the new embedding table.
2. Write a migration to enable the pgvector extension.
3. Write a repository class that inserts and queries vectors.
4. Temporarily keep FAISS in place for comparison.
5. Switch the chatbot retrieval path to the new PostgreSQL vector store.
6. Remove FAISS once the new path is stable.

### Retrieval behavior to preserve

Your current flow expects:

- chunk text,
- metadata,
- vector search results,
- and a fallback path for no results.

The pgvector version should preserve that same contract as much as possible so the chatbot layer does not need a total rewrite.

---

## Phase 3 — File-by-file change map

Below is the practical list of code areas to update.

### 1. Storage implementation

Update:

- `src/database/storage/storage_service.py`
- `src/database/storage/local_file_storage_service.py`
- `src/database/storage/s3_storage_service.py`
- `src/database/storage/storage_service_factory.py`

### 2. API upload/delete flow

Update:

- `src/api/services/document_uploads.py`
- route/controller files that call upload and delete operations

Goal:

- save uploaded bytes to S3,
- delete all S3 objects for a chat when the chat is deleted,
- keep duplicate handling and validation working.

### 3. Database schema

Update:

- `src/database/models.py`
- Alembic migrations in `alembic/versions/`

Goal:

- add vector storage schema,
- keep document metadata relational,
- ensure cascade delete behavior works cleanly.

### 4. Retrieval layer

Update:

- `src/components/retrieval/vector_store.py`
- `src/components/retrieval/faiss_store.py`
- likely a new pgvector-backed vector store module

Goal:

- switch from FAISS index files to SQL vector queries,
- keep the chatbot interface stable where possible.

### 5. Chat / orchestration

Update:

- `src/components/chatbot/core.py`
- `src/components/retrieval/embedder.py`

Goal:

- make sure embeddings still feed the new store correctly,
- preserve the upload → embed → retrieve flow.

### 6. Configuration and deployment

Update:

- `src/config/configs.py`
- `.env`
- `docker-compose.yml`
- `requirements.txt`
- README / deployment notes

Goal:

- make local dev and production behavior explicit,
- document which backend uses local storage versus S3,
- document which vector backend is active.

---

## Suggested implementation order

If you want the least risky path, do this:

1. **S3 first**
   - Implement `S3StorageService`
   - Switch the storage factory
   - Verify upload/delete/cleanup still work

2. **Keep FAISS for now**
   - Do not change vector persistence at the same time
   - Stabilize file storage first

3. **Then migrate vectors to pgvector**
   - Add schema and repository support
   - Swap retrieval implementation

4. **Finally clean up old code**
   - Remove FAISS-specific files only after pgvector works

---

## Practical notes for this project

- Your current design already separates interfaces from concrete implementations, which is good for this migration.
- `StorageService` is already the right abstraction for local disk vs S3.
- The vector side will need more work than the file side because FAISS currently owns both index storage and metadata persistence.
- Once pgvector is in place, you will likely no longer need to manage separate vector files on disk.
- If you want to keep uploads recoverable or auditable, you can still store raw file bytes in S3 even after moving embeddings to PostgreSQL.

---

## Short version

1. Add AWS config and implement S3 storage behind `StorageService`.
2. Switch upload/delete flows to use S3 through the storage factory.
3. Add pgvector support to PostgreSQL with a new embedding table and Alembic migration.
4. Replace FAISS-backed vector persistence with SQL-based vector queries.
5. Update config, dependencies, and deployment files last.


