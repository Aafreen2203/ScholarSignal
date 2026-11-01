# API contracts (v1)

Base path: `/api/v1`. OpenAPI is served at `/api/docs`.

| Method | Endpoint | Request | Response / behavior |
| --- | --- | --- | --- |
| POST | `/auth/register` | `{email, password, display_name}` | 201 user summary; sets HttpOnly session cookie; 409 duplicate email; 422 invalid input; 429 rate limited; 503 Redis unavailable |
| POST | `/auth/login` | `{email, password}` | 200 user summary; sets cookie; 401 generic credential error; 429 rate limited; 503 Redis unavailable |
| POST | `/auth/logout` | none | 204; clears session cookie |
| GET | `/auth/me` | session cookie | 200 user summary; 401 absent/invalid/expired session |
| GET | `/search?q=...&method=lexical&limit=10` | `q` (1–500 chars), `method` (`lexical` or `semantic`), `limit` (1–50) | 200 query, `retrieval_method`, method explanation, scores, and publication results; 503 when the semantic model cannot load |
| GET | `/health/live` | none | 200 process liveness |
| GET | `/health/ready` | none | 200 only when PostgreSQL and Redis respond; otherwise 503 |

User summary fields: `id`, normalized `email`, `display_name`, and
`created_at`. Passwords and hashes are never returned. Browser requests use the
same-origin Next.js proxy and do not expose internal service addresses.

Search responses include actual persisted OpenAlex publication fields (OpenAlex
ID, title, abstract, authors, publication date, DOI, concepts/topics, citation
count, and retrieval score). Lexical search is PostgreSQL English full-text
ranking. Semantic search uses the configured 384-dimensional embedding model
and pgvector cosine distance. Latency and relevance metrics are omitted until a
labelled evaluation set is available. The frontend sends search requests through
the same Next.js `/api/*` proxy used by authentication.

Ingestion is an operator CLI, not a public API route:
`python -m backend.app.ingestion.cli works --filter publication_year:2024 --limit 5`.
Embedding generation is `python -m backend.app.ingestion.cli embeddings`.

