# Design

## API

### Response Wrappers

#### Success Envelope Wrapper

```json
{
    "success": true,
    "message": "...",
    "data": {} | null
}
```

#### Error Envelope Wrapper

```json
{
    "success": false,
    "message": "...",
    "error": { "code": "...", "details": "...", "stack_trace": "..." | null }
}
```

### Health Routes

No auth cookie required.

| Method & Path     | Input           | Output (if successful)       |
|-------------------|-----------------|------------------------------|
| GET `/health/api` | none            | 200, `data={"status": "OK"}` |
| GET `/health/db`  | none (pings DB) | 200, `data={"status": "OK"}` |

### Auth Routes

Excluded from the session-cookie check (this is how sessions are created).

#### Create an anonymous user session

**Endpoint:** `POST /auth/anonymous`

**Input:** No input since the endpoint reads the existing session cookie if present

**Output (if successful):**

```json
{
    "...": "..."
    "data": {
        "userId": "<user-id>"
    }
}
```

Also sets/updates the signed `httpOnly` session cookie in your browser.

### Chat Session Routes

Owner is derived from the session cookie. Prefix `/sessions`.

| Method & Path | Input | Output |
|---|---|---|
| POST `/sessions` | Body: `{title: str}` | 201, `data={"chat_id": str}`. 422 `MAX_CHATS_PER_USER_REACHED` if at the per-user chat limit |
| POST `/sessions/init` | Body: `{title: str}` | 200, `data={"chat_id": str}` — returns the user's most recent session, or creates one if none exists |
| GET `/sessions/{session_id}` | Path: `session_id: UUID` | 200, `data={id, title, created_at}`. 404 `CHAT_SESSION_NOT_FOUND` if not owned/found |
| DELETE `/sessions/{session_id}` | Path: `session_id: UUID` | 200, `data={"chat_id": str}`. 404 if not found |
| GET `/sessions/{session_id}/messages` | Path: `session_id: UUID` | 200, `data=[{id, session_id, role, content, created_at}, ...]` |

### Documents

Prefix `/documents`.

| Method & Path | Input | Output |
|---|---|---|
| GET `/documents` | Query: `chat_id: UUID` | 200, `data={"documents": [{id, session_id, source, source_size, processing_status, created_at, updated_at}, ...]}` |
| POST `/documents` | multipart/form-data: `documents: List[UploadFile]` (1-5 files, extension-validated), `chat_id: UUID` (form field) | 201, `message="Successfully uploaded N document(s)."`. Errors: 422 `INVALID_UPLOAD_REQUEST` / `INVALID_FILE_EXTENSION` / `UNSUPPORTED_FILE_TYPE` / `FILE_SIZE_LIMIT_EXCEEDED`; 409 `DUPLICATE_DOCUMENTS_IN_REQUEST` / `DOCUMENT_ALREADY_EXISTS` / `MAX_DOCUMENTS_PER_CHAT_EXCEEDED`; 404 `CHAT_SESSION_NOT_FOUND` |
| DELETE `/documents/{document_id}` | Path: `document_id: UUID`; Query: `chat_id: UUID` | 200, `message="Successfully deleted the document."`. 404 `DOCUMENT_NOT_FOUND` / `CHAT_SESSION_NOT_FOUND` |

### RAG Chatbot

Prefix `/chat`.

| Method & Path | Input | Output |
|---|---|---|
| POST `/chat` | Body: `{user_query: str (length-bounded, sanitized), chat_id: UUID, web_search_enabled: bool = False}` | 200, `data={answer: str, sources: List[str]}`. 404 `CHAT_SESSION_NOT_FOUND`; 500 `LLM_SERVICE_ERROR` on LLM failure |

## Services

### 1. Auth

Manages anonymous (cookie-based, no-password) user identities: creation,
reuse/renewal, and expiry cleanup.

**Flow:**

1. If no session cookie is present, create a new `User` row and return its id.
2. If a cookie is present, decode/verify it; on any failure or if the
   referenced user no longer exists, fall back to creating a new user.
3. Otherwise, update `last_seen_at` on the existing user and return their id.
4. (Cleanup, run periodically) delete any user whose `last_seen_at` is older
   than the configured TTL.

### 2. Chatbot

Orchestrates a single chat turn end-to-end: RAG retrieval, LLM response
generation, optional live web-search fallback, and persisting the exchange.

**Flow:**

1. Verify the chat session exists and is owned by the caller.
2. Expand the user's query via an LLM to enrich it for retrieval (falls back
   to the original query if expansion fails or returns empty).
3. Embed the (expanded) query and run a pgvector similarity search over the
   chat session's document chunks (top-K, threshold-filtered).
4. Ask the LLM to generate an answer from the retrieved context. The LLM can
   signal one of: a normal answer, out-of-scope, or "needs web search."
5. If web search is needed and enabled (globally and per-request) and the
   per-session web-search quota isn't exhausted: search the web, fetch and
   validate page content (SSRF-safe), extract/chunk/embed it into temporary
   document chunks for the session, then re-run steps 3-4 once more against
   the freshly ingested content.
6. Persist the user's query and the assistant's answer as `ChatMessage` rows.
7. Return `{answer, sources}`.

Note: a cross-encoder reranker component exists in the codebase but is not
currently wired into the retrieval flow (available for future use).

### 3. Chat

CRUD-style management of chat sessions and their message history, always
scoped/authorized by the owning anonymous user.

**Flow:**

1. `create_new_chat`: reject with 422 if the user is already at the max
   chats-per-user limit, otherwise insert a new `ChatSession` row.
2. `init_chat_session`: return the user's most recent session, or create one
   if none exists.
3. `get_chat_metadata` / `delete_chat` / `get_chat_messages`: verify the
   session exists and is owned by the caller (404 otherwise), then perform
   the read/delete and return the result.

### 4. Cleanup

Background scheduler (started at app startup, stopped on shutdown) that
periodically reaps abandoned data.

**Flow:**

1. On a configured interval, delete expired anonymous user sessions (past
   their TTL).
2. Mark documents stuck in a processing state past a timeout as failed.
3. Delete failed documents older than their retention window (cascades to
   their chunks).
4. Delete orphaned web-search document chunks (no owning document) older
   than their retention window.
5. Loop continues until the app shuts down, at which point the scheduler
   stops gracefully rather than mid-sleep.

### 5. Documents

Handles the document ingestion pipeline for uploads, plus listing/deleting
document metadata.

**Flow (upload):**

1. Verify the chat session exists and is owned by the caller.
2. Reject duplicate filenames — both within the same request and against
   filenames already stored for that chat.
3. Reject if adding these files would exceed the max-documents-per-chat
   limit.
4. For each file: clean the filename, read its bytes, reject if it exceeds
   the max file size, and reject (skip) if it would push the chat's
   cumulative storage over its size quota.
5. In a DB transaction, per file: insert a `Document` row, extract its text
   (Docling), chunk it (context-aware chunking), embed the chunks, and store
   them as `DocumentChunk` rows tied to the document and chat session.
6. Return the count of successfully uploaded documents.

**Flow (list / delete):** verify chat ownership, then list or delete the
requested document metadata (delete cascades to its chunks).
