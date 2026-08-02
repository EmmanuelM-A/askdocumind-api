# API Design

Details the design of the API endpoints, including request and response formats,
authentication requirements, route structures, status codes, and error codes.

Backend: FastAPI. All routers are mounted under the prefix **`/api`**. There is no
separate OpenAPI/Swagger file in the repo — FastAPI auto-generates one from these
routes, served at `/api/docs` (Redoc is disabled). This document is the
hand-maintained, human-readable equivalent for frontend integration.

---

## Response Envelopes

Every response (success or error) is wrapped in one of the following shapes.

### Success Envelope

```json
{
    "success": true,
    "timestamp": "<formatted datetime string>",
    "message": "<string>",
    "data": {} | [] | null
}
```

### Error Envelope

```json
{
    "success": false,
    "timestamp": "<formatted datetime string>",
    "message": "<string>",
    "error": {
        "code": "<string>",
        "details": "<string|null>",
        "stack_trace": "<string|null>"
    }
}
```

`stack_trace` is only populated when the server is running with `ENV=development`; treat
it as always `null` in production.

> **Known inconsistency — read before building error handling:** most validation
> failures raised explicitly in application code (via helpers like
> `unprocessable_entity_error`, `conflict_error`, `not_found_error`) return the envelope
> above. However, a few validation paths are enforced directly by Pydantic/FastAPI
> request parsing (malformed UUID path/query params, and the body-level validators on
> `POST /sessions`, `POST /sessions/init`, and `POST /chat`) and **fall through to
> FastAPI's default error shape instead**:
> ```json
> { "detail": [ { "type": "...", "loc": ["body", "field"], "msg": "...", "input": "..." } ] }
> ```
> Both shapes are used for `422` responses depending on the exact cause. The frontend
> should defensively check for `success` on 4xx/5xx bodies before assuming the standard
> envelope, or treat any non-`success`-shaped 422 body as a generic validation error.
>
> Additionally, `429 Too Many Requests` (rate limiting) is returned directly by the
> rate-limiting library and does **not** use the standard envelope either.

### Common error codes reference

| HTTP Status | Meaning | Example `error.code` values |
|---|---|---|
| 401 | Unauthorized | `UNAUTHORIZED` |
| 403 | Forbidden | `FORBIDDEN` |
| 404 | Not found | `NOT_FOUND`, `CHAT_SESSION_NOT_FOUND`, `DOCUMENT_NOT_FOUND`, `ANONYMOUS_USER_NOT_FOUND` |
| 409 | Conflict | `CONFLICT`, `MAX_DOCUMENTS_PER_CHAT_EXCEEDED`, `DUPLICATE_DOCUMENTS_IN_REQUEST`, `DOCUMENT_ALREADY_EXISTS` |
| 413 | Payload too large | `REQUEST_TOO_LARGE` |
| 422 | Unprocessable / validation error | `UNPROCESSABLE_ENTITY`, `NO_COOKIE_VALUE`, `INVALID_USER_SIGNATURE`, `INVALID_UPLOAD_REQUEST`, `INVALID_FILE_EXTENSION`, `UNSUPPORTED_FILE_TYPE`, `FILE_SIZE_LIMIT_EXCEEDED`, `EMPTY_QUERY`, `MAX_CHATS_PER_USER_REACHED` |
| 429 | Too many requests | (rate limiter's own shape, no `code` field) |
| 500 | Server error | `INTERNAL_SERVER_ERROR`, `DOCUMENT_READ_FAILED` |
| 503 | Server busy (concurrency cap) | `SERVER_BUSY` |

---

## Cross-Cutting Behavior (applies to every route below)

### Authentication — anonymous session cookie

There is no login/password/user-account system. Identity is a single **anonymous
session cookie**, automatically issued and rotated by the server.

- **Cookie name:** `askdocumind_user_cookie`
- **Attributes:** `HttpOnly`, `Path=/`, `SameSite` and `Secure` derived from server config
  (defaults to `SameSite=None; Secure`), `Max-Age` = session TTL (default ~60h,
  environment-configurable).
- **Frontend requirement:** requests must be made with `credentials: "include"` (fetch)
  or `withCredentials: true` (axios) so the browser sends/receives the cookie. No
  `Authorization` header is used anywhere in this API.
- The cookie is transparently **rotated on every authenticated request** — always let
  the browser handle it; don't cache/store the token value yourself.
- Routes **excluded** from the cookie check: `OPTIONS` preflight requests,
  `POST /auth/anonymous` (this is how the cookie is first created), and all
  `GET /health/*` routes.
- All other routes require the cookie. If it's missing or invalid, you get a `404`/`422`
  before your route's own logic ever runs — see the table below.

| Condition | Status | `error.code` |
|---|---|---|
| Cookie missing | 422 | `NO_COOKIE_VALUE` |
| Cookie present but signature invalid, malformed, or expired | 422 | `INVALID_USER_SIGNATURE` |
| Cookie valid but the user it references no longer exists in the DB | 404 | `ANONYMOUS_USER_NOT_FOUND` |

### Rate limiting

Per-client rate limits are enforced (keyed by the anonymous user ID once known, else by
IP). Exceeding a limit returns **`429 Too Many Requests`** (not the standard envelope —
see note above). Defaults, all environment-configurable:

| Route group | Default limit |
|---|---|
| `POST /auth/anonymous` | falls under the global default (100 requests / 60s / IP) — no dedicated limit |
| `/sessions/*` | 10 requests / minute |
| `/documents` (GET, POST, DELETE) | 5 requests / minute |
| `POST /chat` | 10 requests / minute |
| `GET /health/api` | 60 requests / minute |
| `GET /health/db` | 30 requests / minute |

### Other global limits

| Limit | Default | Behavior on breach |
|---|---|---|
| Max concurrent in-flight requests | 50 | `503`, `error.code="SERVER_BUSY"` |
| Max request body size | 10 MB | `413`, `error.code="REQUEST_TOO_LARGE"` |

### CORS

`credentials` are allowed (`Access-Control-Allow-Credentials: true`); allowed origins
are configured server-side (`CORS_ORIGINS`). Allowed headers include `Content-Type`,
`Accept-Version`, `Authorization`, `X-Requested-With`.

---

## Health Routes

Prefix: `/health`. No auth cookie required. Not rate-limited beyond the table above.

### Check API health

**`GET /health/api`**

Input: none.

| Status | Condition |
|---|---|
| 200 | Always, unless a global limit (429/503) is hit |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "The API is healthy and running.",
    "data": { "status": "OK" }
}
```

### Check database health

**`GET /health/db`**

Input: none. Pings the database.

| Status | Condition | `error.code` |
|---|---|---|
| 200 | DB reachable | — |
| 500 | DB ping failed | `INTERNAL_SERVER_ERROR` |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Database connectivity check completed.",
    "data": { "status": "OK" }
}
```

---

## Auth Routes

Prefix: `/auth`. Excluded from the session-cookie check — this is how sessions are created.

### Create (or resume) an anonymous user session

**`POST /auth/anonymous`**

**Input:** No body required. If an existing valid session cookie is sent, that user is
reused (`last_seen_at` is refreshed); otherwise — or if the cookie is missing, expired,
or invalid — a brand-new anonymous user is silently created. This endpoint never errors
out on a bad cookie; it just issues a fresh one.

**Response:**

| Status | Condition |
|---|---|
| 201 | Always (new or resumed session) |

```json
// 201
{
    "success": true,
    "timestamp": "...",
    "message": "Anonymous user session created successfully.",
    "data": { "user_id": "<uuid>" }
}
```

Also sets/rotates the `askdocumind_user_cookie` cookie on the response. **Call this
once on app load** (or let `POST /sessions/init` implicitly rely on a cookie already
existing — but calling this first is the safe bootstrap step) before hitting any other
route.

---

## Chat Session Routes

Prefix: `/sessions`. Requires a valid session cookie. Owner is derived from the cookie
(`user_id`), never passed by the client. Rate limit: 10 req/min.

> **Naming note:** these routes use the path param name `session_id`; the documents and
> chat routes below refer to the same value as `chat_id`. They are the same ID
> (`ChatSession.id`).

> **Chat cap:** by default a user may only have **1** chat session at a time
> (`MAX_CHATS_PER_USER`, env-configurable). This is enforced only on `POST /sessions`,
> not on `POST /sessions/init` (see below) — in practice, most frontends should just use
> `POST /sessions/init` as the single entry point.

### Create a chat session

**`POST /sessions`**

**Input:**

```json
{ "title": "<string, required>" }
```

`title` is required (any non-null string; no length constraints enforced server-side).

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 201 | Created | — |
| 422 | User already has the max number of chat sessions | `MAX_CHATS_PER_USER_REACHED` |
| 422 | Missing/invalid `title` in body | — (FastAPI default validation shape, see note above) |

```json
// 201
{
    "success": true,
    "timestamp": "...",
    "message": "Chat session created successfully.",
    "data": { "chat_id": "<uuid>" }
}
```

### Initialize or retrieve a chat session

**`POST /sessions/init`**

Returns the user's most-recently-created session if one exists; otherwise creates a new
one with the given title. **Does not enforce the max-chats-per-user cap.** This is the
recommended endpoint for a frontend's "open the app" flow — it's idempotent from the
caller's perspective.

**Input:**

```json
{ "title": "<string, required>" }
```

Note: if a session already exists, the supplied `title` is ignored (the existing
session's title is returned, not overwritten).

**Response:**

| Status | Condition |
|---|---|
| 200 | Always (whether an existing session was found or a new one created — note: 200, not 201, even on creation) |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Chat session initialized successfully.",
    "data": { "chat_id": "<uuid>" }
}
```

### Get a chat session

**`GET /sessions/{session_id}`**

**Input:** Path — `session_id` (UUID).

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 200 | Found and owned by caller | — |
| 404 | Not found, or exists but belongs to a different user | `CHAT_SESSION_NOT_FOUND` |
| 422 | `session_id` is not a valid UUID | — (FastAPI default validation shape) |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Chat session fetched successfully.",
    "data": {
        "id": "<uuid>",
        "title": "<string|null>",
        "created_at": "<formatted datetime>"
    }
}
```

### Delete a chat session

**`DELETE /sessions/{session_id}`**

**Input:** Path — `session_id` (UUID).

Deleting a session cascades (DB-level) to delete its messages and documents.

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 200 | Deleted | — |
| 404 | Not found / not owned | `CHAT_SESSION_NOT_FOUND` |
| 422 | `session_id` is not a valid UUID | — |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Chat session deleted successfully.",
    "data": { "chat_id": "<uuid>" }
}
```

### Get a chat session's messages

**`GET /sessions/{session_id}/messages`**

**Input:** Path — `session_id` (UUID).

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 200 | Found (returns `[]` if there are no messages yet — not a 404) | — |
| 404 | Session not found / not owned | `CHAT_SESSION_NOT_FOUND` |
| 422 | `session_id` is not a valid UUID | — |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Chat messages fetched successfully.",
    "data": [
        {
            "id": "<uuid>",
            "session_id": "<uuid>",
            "role": "USER" | "ASSISTANT" | "SYSTEM",
            "content": "<string>",
            "sources": ["<string>", "..."] | null,
            "created_at": "<formatted datetime>"
        }
    ]
}
```

`sources` is a snapshot of the document filenames used to generate that specific
message, taken at generation time — it is `null` for `USER`/`SYSTEM` messages, and `[]`
for an `ASSISTANT` message that answered without citing any documents (e.g. a
fallback/no-match response). It is **not** kept in sync with the documents endpoints: if
a cited document is later deleted via `DELETE /documents/{document_id}`, its filename
still appears here unchanged — treat it as a historical record of what was used, not a
live reference. See `POST /chat` below for where this value originates.

---

## Documents Routes

Prefix: `/documents`. Requires a valid session cookie. Owner is derived from the cookie.
Rate limit: 5 req/min.

### List a chat session's documents

**`GET /documents`**

**Input:** Query — `chat_id` (UUID, **required**).

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 200 | OK | — |
| 404 | Chat not found / not owned by caller | `CHAT_SESSION_NOT_FOUND` |
| 422 | `chat_id` missing or not a valid UUID | — |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Successfully fetched N document(s).",
    "data": {
        "documents": [
            {
                "id": "<uuid>",
                "session_id": "<uuid>",
                "source": "<filename>",
                "source_size": 12345,
                "source_type": "UPLOAD" | "WEB_SEARCH",
                "processing_status": "PROCESSING" | "COMPLETED" | "FAILED",
                "created_at": "<formatted datetime>",
                "updated_at": "<formatted datetime>"
            }
        ]
    }
}
```

### Upload documents

**`POST /documents`**

**Input:** `multipart/form-data`:

| Field | Type | Required | Constraints |
|---|---|---|---|
| `documents` | file[] | yes | 1–5 files per request. Allowed extensions: `.pdf`, `.docx`, `.txt`, `.md`, `.html`, `.csv` (case-insensitive). Files with multiple extensions (e.g. `file.tar.gz`) are rejected. Max **0.5 MB** per file. |
| `chat_id` | UUID (string) | yes | must reference a chat session owned by the caller |

Additional server-side limits:
- Max **10** documents total per chat session.
- Max **1 MB** total document bytes per chat session — if a chat is already near its
  cap, individual incoming files that would exceed it are **silently dropped** (not
  saved, no per-file error returned); only the count of files actually saved is
  reported back (`quantity_uploaded`). Don't assume every filename you sent was stored —
  re-fetch via `GET /documents` to confirm what landed.
- Duplicate filenames (case-insensitive) are rejected, both within the same request and
  against documents already present in the chat.
- The whole multipart body is still subject to the global 10 MB request-size cap
  (returns `413` if exceeded, checked before this route's own 0.5 MB/file check runs).

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 201 | At least the request was accepted and processed (see note on silent drops above) | — |
| 404 | Chat not found / not owned | `CHAT_SESSION_NOT_FOUND` |
| 409 | Uploading would exceed the 10-documents-per-chat cap | `MAX_DOCUMENTS_PER_CHAT_EXCEEDED` |
| 409 | Two or more files in this request share a name | `DUPLICATE_DOCUMENTS_IN_REQUEST` |
| 409 | A file name already exists for this chat | `DOCUMENT_ALREADY_EXISTS` |
| 422 | 0 files or more than 5 files provided | `INVALID_UPLOAD_REQUEST` |
| 422 | File has multiple extensions | `INVALID_FILE_EXTENSION` |
| 422 | File extension not in the allowed list | `UNSUPPORTED_FILE_TYPE` |
| 422 | A file exceeds the per-file size limit | `FILE_SIZE_LIMIT_EXCEEDED` |
| 413 | Whole multipart body exceeds the global 10 MB cap | `REQUEST_TOO_LARGE` |
| 500 | Server-side error reading uploaded file bytes | `DOCUMENT_READ_FAILED` |

```json
// 201
{
    "success": true,
    "timestamp": "...",
    "message": "Successfully uploaded N document(s).",
    "data": null
}
```

### Delete a document

**`DELETE /documents/{document_id}`**

**Input:** Path — `document_id` (UUID). Query — `chat_id` (UUID, **required**).

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 200 | Deleted | — |
| 404 | Chat not found / not owned | `CHAT_SESSION_NOT_FOUND` |
| 404 | Document not found for that chat | `DOCUMENT_NOT_FOUND` |
| 422 | `document_id` or `chat_id` missing/invalid | — |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Successfully deleted the document.",
    "data": null
}
```

---

## RAG Chatbot Routes

Prefix: `/chat`. Requires a valid session cookie. Owner is derived from the cookie.
Rate limit: 10 req/min.

### Send a chat query

**`POST /chat`**

**Input:**

```json
{
    "user_query": "<string, required>",
    "chat_id": "<uuid, required>",
    "web_search_enabled": false
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `user_query` | string | yes | length between `MIN_QUERY_LENGTH` (default 10) and `MAX_QUERY_LENGTH` (default 2000) chars after server-side sanitization (HTML tags stripped, scripts/`javascript:`/`eval(`-style patterns stripped, whitespace collapsed). Empty/whitespace-only after cleanup is rejected. |
| `chat_id` | UUID | yes | must reference a chat session owned by the caller |
| `web_search_enabled` | boolean | no | default `false`; when `true`, the RAG pipeline augments retrieval with a live web search |

**Response:**

| Status | Condition | `error.code` |
|---|---|---|
| 200 | Answer generated | — |
| 404 | Chat not found / not owned | `CHAT_SESSION_NOT_FOUND` |
| 422 | `user_query` empty after sanitization | `EMPTY_QUERY` (may surface via the FastAPI-default validation shape rather than the standard envelope — see the note at the top of this document) |
| 422 | `user_query` shorter/longer than the allowed length, or `chat_id` invalid | — (FastAPI default validation shape) |
| 500 | Unhandled error in the retrieval/LLM/web-search pipeline | `INTERNAL_SERVER_ERROR` |

```json
// 200
{
    "success": true,
    "timestamp": "...",
    "message": "Chatbot response generated successfully.",
    "data": {
        "answer": "<string>",
        "sources": ["<string>", "..."]
    }
}
```

On success, both the user's message and the assistant's reply are persisted — including
this response's `sources` array, saved onto the assistant's `ChatMessage.sources` — and
will subsequently appear via `GET /sessions/{session_id}/messages`. This is what lets
the frontend redisplay sources after a page refresh without re-deriving them from
`GET /documents`.
