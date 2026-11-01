# ScholarSignal architecture

## Current application path

```text
Next.js App Router
  ├─ Search UI ────────────────> same-origin /api proxy ──> FastAPI search/detail
  ├─ Protected research desk ──> same-origin /api proxy ──> FastAPI workspace
  └─ Auth forms and SSR route guard ──────────────────────> FastAPI auth
FastAPI ──> SQLAlchemy 2 ──> PostgreSQL + pgvector
FastAPI auth limits ──────────> Redis
Operator CLI ──> budget guarded OpenAlex client ──> resumable PostgreSQL upserts
FastEmbed (local ONNX) ───────> persisted vectors, query retrieval, related papers
Versioned relevance judgments ──> local evaluation CLI ──> P@3 / Recall@3 / MRR / nDCG@3
```

The frontend owns presentation and user interaction. FastAPI owns validation,
authorization, search and persistence. Search is public over the locally stored
corpus; user history is written only for valid authenticated sessions. No
browser code receives OpenAlex credentials, model weights, or service URLs.

## Search and ML

Lexical retrieval uses PostgreSQL English `tsvector` ranking on title and
abstract. Semantic retrieval generates one query vector locally with
FastEmbed `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions) and ranks
current, complete publication vectors with pgvector cosine distance. HNSW
indexes support vector retrieval. Hybrid ranking uses reciprocal-rank fusion
with a maximum of 1,000 candidates per method and reports when the candidate
set was capped. Results include actual stored metadata, scores and method
explanations. Sort and metadata filters are applied in the API/service layer;
semantic date/citation ordering covers the entire filtered vector set before
pagination.

Related-paper results compare a publication's persisted vector with vectors
already stored locally. They do not call OpenAlex or another model service.
Topic/concept data and references are source metadata, not generated
recommendation explanations. The evaluation dataset is an explicitly
single-annotator pilot over the five existing records; no production-quality
relevance claim is made. Author/topic filters currently use `ILIKE` over
serialized JSON metadata and are not index-backed; treat them as a small-corpus
feature pending normalization/indexing and realistic query-plan benchmarks.

## User data and security

Passwords are Argon2 hashes. Authentication uses an expiring signed JWT in an
HttpOnly, SameSite=Lax cookie. Production requires an explicit strong
`JWT_SECRET`, HTTPS, `COOKIE_SECURE=true`, and the exact frontend origin.
Registration and login rate limits use atomic Redis counters keyed with a
SHA-256 digest of normalized email; auth fails closed if Redis is unavailable.
There is no IP-based rate limit or server-side JWT revocation yet.

Workspace records are owner-scoped in every query. Saved papers and
collection memberships have uniqueness constraints; notes, collections,
views, and search history are persisted in PostgreSQL. Search history keeps at
most 200 recent records per user. Foreign-key cascades clean up dependent
private rows when a user, collection, or publication is deleted. Public source
publications are not user-owned.

## Persistence, ingestion and operational boundaries

Alembic migrations own all schema changes. PostgreSQL stores users, real
OpenAlex publications, raw source provenance, per-source ingestion jobs,
budget/usage events, model-versioned vectors, and workspace state. Redis is
used for authentication limits. Compose mounts persistent PostgreSQL and model
cache volumes.

OpenAlex ingestion is an explicit, bounded CLI operation. The client uses
Bearer authentication, pagination, retry/backoff, durable checkpoints, and a
persistent usage ledger with a $0.10 per-UTC-day project ceiling. No ingestion
starts at app startup or in an HTTP request. Do not resume the saved cursor or
launch more ingestion without explicit approval. Embedding generation is also
an explicit local CLI operation and is idempotent for unchanged text/model
versions. Search requests do local inference only.

## Deployment boundary

Docker Compose is the verified local runtime and applies Alembic migrations
before starting FastAPI. GitHub Actions defines PostgreSQL/Redis integration
services and browser checks, but this checkout has no observed hosted Actions
run. There is no production deployment, backup automation, external queue, or
background ingestion worker. Those are deployment/operations work rather than
features that should silently trigger paid or unbounded source access.
