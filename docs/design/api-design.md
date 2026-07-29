# API Design

Details the design of the API endpoints, including request and response formats,
authentication requirements, and route structures.

## Response Wrappers

### Success Envelope Wrapper

```json
{
    "success": true,
    "message": "...",
    "data": {} | null
}
```

### Error Envelope Wrapper

```json
{
    "success": false,
    "message": "...",
    "error": { "code": "...", "details": "...", "stackTrace": "..." | null }
}
```

## Health Routes

No auth cookie required.

| Method & Path     | Input           | Output (if successful)       |
|-------------------|-----------------|------------------------------|
| GET `/health/api` | none            | 200, `data={"status": "OK"}` |
| GET `/health/db`  | none (pings DB) | 200, `data={"status": "OK"}` |

## Auth Routes

Excluded from the session-cookie check (this is how sessions are created).

### Create an anonymous user session

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

## Chat Session Routes

Owner is derived from the session cookie. Prefix `/sessions`.

### Create a chat session

**Endpoint:** `POST /sessions`

**Input:**

```json
{
    "title": "<title>"
}
```

**Output (if successful):**

```json
{
    "...": "...",
    "data": {
        "chatId": "<chat-id>"
    }
}
```

### Initialize or retrieve a chat session

**Endpoint:** `POST /sessions/init`

**Input:**

```json
{
    "title": "<title>"
}
```

**Output (if successful):** Returns the user's most recent session, or creates one if none exists.

```json
{
    "...": "...",
    "data": {
        "chatId": "<chat-id>"
    }
}
```

### Get a chat session

**Endpoint:** `GET /sessions/{sessionId}`

**Input:** Path: `sessionId`

**Output (if successful):**

```json
{
    "...": "...",
    "data": {
        "id": "<chat-id>",
        "title": "<title>",
        "createdAt": "<timestamp>"
    }
}
```

### Delete a chat session

**Endpoint:** `DELETE /sessions/{sessionId}`

**Input:** Path: `sessionId`

**Output (if successful):**

```json
{
    "...": "...",
    "data": {
        "chatId": "<chat-id>"
    }
}
```

### Get a chat session's messages

**Endpoint:** `GET /sessions/{sessionId}/messages`

**Input:** Path: `sessionId`

**Output (if successful):**

```json
{
    "...": "...",
    "data": [
        {
            "id": "<message-id>",
            "sessionId": "<chat-id>",
            "role": "<user|assistant|system>",
            "content": "<content>",
            "createdAt": "<timestamp>"
        }
    ]
}
```

## Documents Routes

Owner is derived from the session cookie. Prefix `/documents`.

### List a chat session's documents

**Endpoint:** `GET /documents`

**Input:** Query: `chatId`

**Output (if successful):**

```json
{
    "...": "...",
    "data": {
        "documents": [
            {
                "id": "<document-id>",
                "sessionId": "<chat-id>",
                "source": "<source>",
                "sourceSize": "<size-in-bytes>",
                "processingStatus": "<status>",
                "createdAt": "<timestamp>",
                "updatedAt": "<timestamp>"
            }
        ]
    }
}
```

### Upload documents

**Endpoint:** `POST /documents`

**Input:** multipart/form-data:

```text
documents: <1-5 files>
chatId: "<chat-id>"
```

**Output (if successful):**

```json
{
    "...": "...",
    "message": "Successfully uploaded N document(s)."
}
```

### Delete a document

**Endpoint:** `DELETE /documents/{documentId}`

**Input:** Path: `documentId`; Query: `chatId`

**Output (if successful):**

```json
{
    "...": "...",
    "message": "Successfully deleted the document."
}
```

## RAG Chatbot Routes

Owner is derived from the session cookie. Prefix `/chat`.

### Send a chat query

**Endpoint:** `POST /chat`

**Input:**

```json
{
    "userQuery": "<query>",
    "chatId": "<chat-id>",
    "webSearchEnabled": false
}
```

**Output (if successful):**

```json
{
    "...": "...",
    "data": {
        "answer": "<answer>",
        "sources": ["<source>"]
    }
}
```
