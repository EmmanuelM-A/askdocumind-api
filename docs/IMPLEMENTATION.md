# IMPLEMENTATION.md

# Implementation Plan - DocuChatAPI (MVP Version)

This document outlines the simplified and achievable implementation plan for the **DocuChatAPI (MVP)** project. 
It builds upon your existing RAG chatbot logic and focuses on turning it into a lightweight API and frontend showcase.

---

## 🧱 Technology Stack

| Component             | Technology             | Purpose                            |
|-----------------------|------------------------|------------------------------------|
| **Backend Framework** | FastAPI                | REST API + async support           |
| **Database**          | PostgresSQL            | Persistent data storage            |
| **ORM**               | SQLAlchemy (async)     | Database models and CRUD           |
| **File Processing**   | PyMuPDF, python-docx   | Extract text from PDFs/DOCs        |
| **Vector Store**      | FAISS (local)          | Embedding-based document retrieval |
| **Frontend**          | React + Tailwind CSS   | Minimal chat + upload interface    |
| **LLM API**           | OpenAI API             | Question answering                 |
| **Deployment**        | Docker + Render/Vercel | Cloud or local deployment          |

---

## Phase 1: Foundation Setup (Week 1) :checkered_flag:

### 1.1 Project Structure & Environment check (COMPLETE)

**Goal:** Establish a clean and reusable project foundation.

| Sub-Phase | Task                             | Deliverable                                            |
|-----------|----------------------------------|--------------------------------------------------------|
| 1.1a      | Initialize FastAPI app structure | `/src`, `/app`, `/api`, `/db`, `/services` directories |
| 1.1b      | Configure environment settings   | `.env` file + Pydantic settings class                  |
| 1.1c      | Setup Docker Compose (optional)  | Postgres container + API container                     |
| 1.1d      | Add logging and error handling   | Centralized structured logger                          |

**Checkpoints:**
- FastAPI runs successfully (`/health` endpoint)
- DB connection verified
- Logging outputs to console and file

### 1.2 Database Initialization (COMPLETE)

**Goal:** Create essential tables for documents, sessions, and messages.

| Sub-Phase | Task                          | Deliverable                              |
|-----------|-------------------------------|------------------------------------------|
| 1.2a      | Setup SQLAlchemy + Alembic    | Database migrations ready                |
| 1.2b      | Create minimal models         | `Document`, `ChatSession`, `ChatMessage` |
| 1.2c      | Add seeding script (optional) | Test data for local dev                  |

**Checkpoints:**
- Tables created successfully
- CRUD tests for basic models

---

## Phase 2: RAG API Integration (Week 2)

**Goal:** Wrap the existing RAG chatbot logic into a reusable API.

| Sub-Phase | Task                              | Description                                      |
|-----------|-----------------------------------|--------------------------------------------------|
| 2.1a      | Create `RAGService` class         | Encapsulate embedding + retrieval logic          |
| 2.1b      | Implement `/api/v1/chat` endpoint | Accept question + session ID + optional document |
| 2.1c      | Add text extraction logic         | Handle PDF, DOCX, TXT files                      |
| 2.1d      | Store temporary embeddings        | Use FAISS locally for retrieval                  |

**Deliverable:** `/chat` endpoint returns AI-generated answers using uploaded documents.

---

## Phase 3: Document Upload System (Week 3)

**Goal:** Enable file uploads and associate them with sessions.

| Sub-Phase | Task                        | Description                             |
|-----------|-----------------------------|-----------------------------------------|
| 3.1       | `/upload` endpoint          | Accept and validate user-uploaded files |
| 3.2       | Extract text and embed      | Use PyMuPDF/docx + OpenAI embeddings    |
| 3.3       | Save metadata               | Store filename, text, vector path       |
| 3.4       | Retrieve uploaded documents | `/documents` endpoint lists all uploads |

**Deliverable:** User can upload a document, which is processed and ready for chat.

---

## Phase 4: Chat Sessions (Week 4)

**Goal:** Persist and organize conversation history.

| Sub-Phase | Task                       | Description                              |
|-----------|----------------------------|------------------------------------------|
| 4.1       | Create `ChatSession` table | Simple session storage with title + date |
| 4.2       | Add `ChatMessage` table    | Save each Q&A exchange                   |
| 4.3       | `/sessions` API            | CRUD endpoints for sessions              |
| 4.4       | `/sessions/{id}/messages`  | Retrieve all messages per session        |

**Deliverable:** Conversations are saved and retrievable.

---

## Phase 5: Frontend Integration (Week 5)

**Goal:** Build a minimal but interactive interface.

| Component      | Feature                                 |
|----------------|-----------------------------------------|
| File Upload UI | Upload documents to the backend         |
| Chat UI        | Send questions and display AI responses |
| Session List   | View all chat sessions                  |

**Deliverable:** Fully functional single-page web interface (React or plain JS + Tailwind).

---

## Phase 6: Deployment & Showcase (Week 6)

| Task              | Description                              |
|-------------------|------------------------------------------|
| Dockerize backend | Create Dockerfile and docker-compose.yml |
| Deploy API        | Use Render, Railway, or Fly.io           |
| Deploy frontend   | Use Vercel or Netlify                    |
| Public demo       | Ensure working example for portfolio     |

**Deliverable:** Deployed demo + GitHub repository with instructions.

---

## ✅ Success Criteria

| Phase | Goal                                  |
|-------|---------------------------------------|
| 1     | FastAPI + DB setup successful         |
| 2     | Chat endpoint returns AI responses    |
| 3     | File uploads and text extraction work |
| 4     | Chat history saved per session        |
| 5     | Frontend connects to API successfully |
| 6     | App deployed and shareable online     |
