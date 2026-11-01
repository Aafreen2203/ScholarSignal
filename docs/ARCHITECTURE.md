# ScholarSignal architecture

## Current vertical slice

```text
Next.js App Router (browser)
  ├─ Same-origin /api proxy ──> FastAPI /api/v1
  └─ Server-rendered protected workspace ──> FastAPI /api/v1/auth/me
FastAPI ──> SQLAlchemy 2 ──> PostgreSQL / pgvector
Ingestion CLI ──> OpenAlex API ──> checkpointed publication upserts
Embedding CLI and search API ──> FastEmbed ──> pgvector HNSW
FastAPI configuration ──> Redis connection boundary (auth rate limits)
```

The repository is a modular monorepo. The frontend owns presentation and form
state; FastAPI owns validation, authentication, search rules, and persistence.
Ingestion and embedding generation are operator-run CLI tasks. The browser does
not receive OpenAlex credentials, embedding model weights, or internal service
URLs.

## Security and session design

Passwords are hashed with Argon2 using `pwdlib`. Authentication is an expiring
JWT in an HttpOnly, SameSite=Lax cookie. The Next.js same-origin route forwards
auth calls and cookie headers to the API. Protected server rendering checks the
cookie against `/auth/me`. Production deployments must set a strong
`JWT_SECRET`, enable `COOKIE_SECURE`, use HTTPS, and configure the exact frontend
origin. Registration validates email/password/name through Pydantic and handles
duplicate email races at the database constraint. Login attempts are limited to
10 per normalized email per 15 minutes and registration attempts to 5 per
normalized email per hour using atomic Redis counters. Keys contain a SHA-256
digest rather than the email address. Authentication fails with 503 if Redis is
unavailable; the readiness endpoint checks both PostgreSQL and Redis.

## Persistence and migrations

SQLAlchemy models and Alembic migrations define the schema. PostgreSQL is the
source of truth for accounts, OpenAlex publications, per-filter ingestion
checkpoints, and model-versioned embeddings. A unique OpenAlex ID makes source
rescans idempotent. Publications retain retrieval time and the raw source
record. pgvector stores 384-dimensional vectors and supports indexed cosine
search. Redis supports authentication rate limits; ingestion is deliberately
not queued or scheduled in this milestone.

## Service boundaries and next milestones

OpenAlex ingestion remains an operator CLI and never runs in a request handler.
The search API performs bounded retrieval and query embedding inference
server-side. The frontend calls it through the established same-origin proxy.
Graph construction, personalization, Kafka, PySpark, advanced ranking, and
scheduled/background ingestion remain out of scope.

