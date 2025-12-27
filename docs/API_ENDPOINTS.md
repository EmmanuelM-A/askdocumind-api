# API_ENDPOINTS.md

## DocuChatAPI (MVP) — API Endpoints

All endpoints are prefixed with `/api/v1/`.

### 🧩 Document Upload
| Method | Endpoint     | Description                        |
|--------|--------------|------------------------------------|
| POST   | `/upload`    | Upload a document (PDF, DOCX, TXT) |
| GET    | `/documents` | List all uploaded documents        |

### 💬 Chat Interaction
| Method | Endpoint | Description                           |
|--------|----------|---------------------------------------|
| POST   | `/chat`  | Ask a question using the RAG pipeline |

### 📚 Chat Sessions
| Method | Endpoint                  | Description                |
|--------|---------------------------|----------------------------|
| GET    | `/sessions`               | List all chat sessions     |
| POST   | `/sessions`               | Create a new chat session  |
| GET    | `/sessions/{id}`          | Get details of a session   |
| DELETE | `/sessions/{id}`          | Delete a session           |
| GET    | `/sessions/{id}/messages` | Get messages for a session |

### 🛠️ Health & Utility
| Method | Endpoint  | Description          |
|--------|-----------|----------------------|
| GET    | `/health` | Health check for API |
