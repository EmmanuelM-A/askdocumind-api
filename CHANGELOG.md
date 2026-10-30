# Changelog

## 2.0.0 — 2026-10-30

A rewrite of the backend since 1.0.0. The routes have changed, so clients
written for 1.0.0 need updating.

### Added

- Several chats per user (up to 5), each with its own files.
- Uploads are stored in S3-compatible storage and processed in the
  background. You can check a file's status, reprocess a failed file, delete
  one file or delete a whole chat with its files.
- `POST /v1/chatbot/{chat_id}/ask` answers from a chat's files and returns
  the names of the files and web pages it used.
- Code files (`.py`, `.js`, `.ts`, `.java`, `.go` and others) and HTML can be
  uploaded, alongside PDF, Word, text and Markdown.
- Expired anonymous users are cleaned up automatically, together with their
  chats and files.
- A `Dockerfile`, with an optional smaller build without the reranker.

### Changed

- Routes are versioned under `/v1`, and documents are now under `/uploads`.
- Similarity search runs in PostgreSQL with pgvector.
- The file size limit is now 10 MB per file.
- Every package in the requirements files is pinned to an exact version.

### Fixed

- Uploading a file with the same name as an existing one returns 409 instead
  of 500.
- The web search fallback blocks private addresses and limits redirects,
  page size and download time.
