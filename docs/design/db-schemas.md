# Database Schemas

Details the database schemas for the AskDocuMind application, including tables, columns, constraints, and relationships.

## User Table

`user`

| Column         | Type        | Constraints                    |
| -------------- | ----------- | ------------------------------ |
| `id`           | UUID        | Primary key, default `uuid4()` |
| `created_at`   | timestamptz | Indexed, default now           |
| `last_seen_at` | timestamptz | Indexed, default now           |

**Relationships:**

- Has many `ChatSession` (one user -> many chat sessions), via `chat_session.user_id`, `ON DELETE CASCADE` — deleting a user deletes all their chat sessions (and, transitively, their documents/chunks/messages).

## ChatSession Table

`chat_session`

| Column       | Type        | Constraints                                             |
| ------------ | ----------- | ------------------------------------------------------- |
| `id`         | UUID        | Primary key, default `uuid4()`                          |
| `user_id`    | UUID        | Foreign key -> `user.id`, `ON DELETE CASCADE`, not null |
| `title`      | text        | Nullable                                                |
| `created_at` | timestamptz | Default now                                             |

**Relationships:**

- Belongs to one `User` via `user_id`.
- Has many `Document` (`documents`), cascade delete-orphan — deleting a chat session deletes its documents.
- Has many `ChatMessage` (`messages`), cascade delete-orphan — deleting a chat session deletes its messages.
- Has many `DocumentChunk` indirectly through `Document`, and directly via `document_chunk.chat_session_id` (used for web-search chunks that have no owning `Document`).

## Document Table

`document`

| Column              | Type                                       | Constraints                                                     |
| ------------------- | ------------------------------------------ | --------------------------------------------------------------- |
| `id`                | UUID                                       | Primary key, default `uuid4()`                                  |
| `session_id`        | UUID                                       | Foreign key -> `chat_session.id`, `ON DELETE CASCADE`, not null |
| `source`            | varchar(255)                               | Not null                                                        |
| `source_size`       | bigint                                     | Not null                                                        |
| `processing_status` | enum (`PROCESSING`, `COMPLETED`, `FAILED`) | Not null                                                        |
| `created_at`        | timestamptz                                | Default now                                                     |
| `updated_at`        | timestamptz                                | Default now, updated on update                                  |

**Table-level constraints:**

- Unique constraint `uq_document_session_source` on (`session_id`, `source`) — a chat session cannot have two documents with the same source.

**Relationships:**

- Belongs to one `ChatSession` via `session_id`.
- Has many `DocumentChunk` (`chunks`), cascade delete-orphan — deleting a document deletes its chunks.

## DocumentChunk Table

`document_chunk`

| Column            | Type         | Constraints                                                     |
| ----------------- | ------------ | --------------------------------------------------------------- |
| `id`              | UUID         | Primary key, default `uuid4()`                                  |
| `document_id`     | UUID         | Foreign key -> `document.id`, `ON DELETE CASCADE`, nullable     |
| `chat_session_id` | UUID         | Foreign key -> `chat_session.id`, `ON DELETE CASCADE`, not null |
| `chunk_text`      | text         | Not null                                                        |
| `embedding`       | vector(1536) | Not null                                                        |
| `created_at`      | timestamptz  | Default now                                                     |

**Relationships:**

- Belongs to one `Document` via `document_id` (nullable — chunks ingested from a web search are tied only to a `chat_session_id`, with no owning `Document` row, and are cleaned up separately as "orphaned" chunks).
- Belongs to one `ChatSession` via `chat_session_id`.

## ChatMessage Table

`chat_message`

| Column       | Type                                 | Constraints                                                     |
| ------------ | ------------------------------------ | --------------------------------------------------------------- |
| `id`         | UUID                                 | Primary key, default `uuid4()`                                  |
| `session_id` | UUID                                 | Foreign key -> `chat_session.id`, `ON DELETE CASCADE`, not null |
| `role`       | enum (`USER`, `ASSISTANT`, `SYSTEM`) | Not null                                                        |
| `content`    | text                                 | Not null                                                        |
| `created_at` | timestamptz                          | Default now                                                     |

**Relationships:**

- Belongs to one `ChatSession` via `session_id`.
