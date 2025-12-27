# DATABASE_DESIGN.md

## Database Design — DocuChatAPI (MVP)

This simplified schema supports single-user operation with essential RAG functionality only.

### 🧾 `Document`

Holds user-uploaded documents that are linked to sessions and embedded for retrieval.

| Column              | Type         | Constraints                                                                 | Purpose                    |
|---------------------|--------------|-----------------------------------------------------------------------------|----------------------------|
| `id`                | UUID (PK)    | Primary Key                                                                 | Unique document identifier |
| `session_id`        | UUID (FK)    | References `ChatSession(id)` ON DELETE CASCADE                              | Parent session             |
| `filename`          | VARCHAR(255) | Not Null                                                                    | Original filename          |
| `file_size`         | BIGINT       | Not Null                                                                    | File size in bytes         |
| `content`           | TEXT         | Not Null                                                                    | Extracted text content     |
| `vector_id`         | VARCHAR(255) | Nullable                                                                    | Vector store reference     |
| `processing_status` | ENUM         | Values: pending, processing, completed, failed; Not Null; Default = pending | Processing state           |
| `created_at`        | TIMESTAMP    | Default = now()                                                             | Upload time                |
| `updated_at`        | TIMESTAMP    | Default = now(), on update set to now()                                     | Last modification          |

### 💬 `ChatSession`

Defines a chat session to group related messages and documents.

| Column           | Type      | Constraints                                   | Description                    |
|------------------|-----------|-----------------------------------------------|--------------------------------|
| `id`             | UUID (PK) | Primary Key                                   | Unique session ID              |
| `title`          | TEXT      | Nullable                                      | Auto-generated or user-defined |
| `total_messages` | INT       | Not Null; Default = 0                         | Cached message count           |
| `created_at`     | TIMESTAMP | Default = now() (timezone-aware recommended)  | Session creation time          |

Constraints: Deleting a `ChatSession` will cascade-delete related `ChatMessage` and `Document` rows (ON DELETE CASCADE).
The `total_messages` field is a cached counter and should default to 0 and not be nullable.

### 🗨️ `ChatMessage`

| Column       | Type      | Constraints                                              | Description          |
|--------------|-----------|----------------------------------------------------------|----------------------|
| `id`         | UUID (PK) | Primary Key                                              | Unique message ID    |
| `session_id` | UUID (FK) | References `ChatSession(id)` ON DELETE CASCADE; Not Null | Parent session       |
| `role`       | TEXT      | Not Null; Enum values: `user`, `assistant`, `system`     | Message role         |
| `content`    | TEXT      | Not Null                                                 | Message text content |
| `created_at` | TIMESTAMP | Default = now() (timezone-aware recommended)             | Message timestamp    |

Constraints: `ChatMessage.session_id` is required and references `ChatSession(id)`; when the parent session is deleted, 
messages are removed via cascade. All message content and role fields are required.

---

## Relationships
- **ChatSession → ChatMessage**: One-to-many (ON DELETE CASCADE)
- **ChatSession → Document**: One-to-many (ON DELETE CASCADE)

---

## Future Expandability (Post-MVP)
- Add `User` table for authentication
- Add `UsageStats` for token tracking
- Add `Plan` for subscription management
- Add `DocumentChunk` for fine-grained retrieval
