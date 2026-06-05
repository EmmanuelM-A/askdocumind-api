# Optimization and Launch Checklist

## 1) Must Complete Before Demo Launch (Backend Integration + Deployment)

1. ~~**Session Identity (Anonymous)** - Add a minimal anonymous user/session model (`id`, `created_at`, `last_seen_at`, optional `expires_at`) 
and persist a session identifier in browser storage/cookie.~~
2. ~~**Session Security** - Sign session tokens (or use signed HTTP-only cookie) so users cannot spoof another session ID.~~
3. ~~**Resource Limits** - Enforce per-session limits (uploads, file size, chats, query frequency) and keep API rate limiting
enabled to prevent abuse.~~
4. ~~**TTL Cleanup Jobs** - Add scheduled cleanup (for inactive sessions) that removes all related resources: DB rows,
uploaded files, vector indexes, metadata, and cache entries.~~
5. ~~**Storage Delete Correctness** - Ensure chat deletion removes full chat storage namespace and vectors, not only partial file items.~~
6. ~~**Validation Coverage** - Ensure all API endpoints use Pydantic request/response schemas consistently.~~
7. ~~**Error Contract Stability** - Standardize API error responses and error codes for predictable frontend integration.~~
8. **Core Observability** - Add structured logging + basic monitoring (request count, failure rate, latency, cleanup outcomes).
9. **Deployment Config Hygiene** - Harden environment/config management for dev/staging/prod, including secrets and runtime flags.
10. **Pre-Launch Tests** - Add/expand integration and e2e tests for chat, upload, retrieval, cleanup, and session lifecycle paths.
11. **Frontend + Deployment** - Setup frontend and integration and deployment envs
12. **GitHub Actions** - Set up a main and development branch with branch checks. CI pipeline for testing and linting
CD pipeline for deploying to prod
13. **Cleanup and polishing** - Cleanup code and make 


## 2) High Priority Right After Demo Launch

1. **Pagination** - Implement pagination for list endpoints.
2. **Caching Improvements** - Cache frequently read metadata/session info to reduce DB load.
3. **DB Performance** - Add DB indexes and optimize common query paths.
4. **Async Throughput Improvements** - Improve asynchronous handling for uploads and chat processing.
5. **Pipeline Parallelization** - Parallelize extraction/embedding where safe to improve ingest performance.

## 3) Medium Priority Refactors

1. **Naming Consistency** - Rename `chatSession` to `chat` for consistent terminology.
2. **Vector Store Strategy** - Evaluate long-term vector store strategy (current FAISS optimizations vs dedicated vector DB).

## Notes

- Demo goal remains valid without full account auth, but anonymous session identity + strict limits + cleanup are required for safe public usage.
- Cleanup should be idempotent and safe to rerun (especially for storage/vector deletions).
