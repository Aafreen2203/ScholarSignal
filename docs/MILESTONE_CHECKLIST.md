# Milestone checklist

## Milestone 1 — platform foundation and authentication

- [x] Establish monorepo boundaries, pinned dependencies, environment template,
  Python/npm locks, and architecture/deployment documentation.
- [x] Create the Next.js App Router shell with landing, registration, login,
  protected workspace, and responsive design system.
- [x] Create FastAPI v1 auth routes, schemas, OpenAPI docs, liveness, and
  database/Redis readiness checks.
- [x] Implement SQLAlchemy user persistence and the initial Alembic migration.
- [x] Hash passwords with Argon2 and use expiring HttpOnly SameSite cookies.
- [x] Rate-limit login and registration by normalized-email hash with atomic
  Redis counters; fail closed when Redis is unavailable.
- [x] Reject the development JWT secret and insecure cookies in production.
- [x] Add PostgreSQL/Redis Compose services, API/frontend Dockerfiles, and
  developer commands.
- [x] Add GitHub Actions service containers for PostgreSQL 17 and Redis 7.4;
  the job migrates PostgreSQL before pytest and runs the service-backed API and
  browser integration suites. **Workflow configuration is present; a hosted
  GitHub Actions run has not been observed.**
- [x] Verify Docker Engine 29.9.2 / Docker Desktop 4.97.0 and Compose 5.6.1.
- [x] Build both Compose application images. The frontend production build and
  backend runtime dependency install both completed successfully.
- [x] Start the existing Compose stack. PostgreSQL 17.11 and Redis 7.4.12
  reported healthy; `/health/ready` reported both dependencies reachable.
- [x] Run `alembic upgrade head` inside the backend image against Compose
  PostgreSQL; `alembic current` reported `0001_users (head)`.
- [x] Add four Playwright browser scenarios for registration/session refresh,
  login, protected-route redirects, logout, and Next.js proxy rate-limit headers.
- [x] Fix logout browser behavior: the workspace now calls the logout API and
  navigates to login after the proxied 204 response.
- [x] Route `/api/*` through the explicit Next.js catch-all proxy handler;
  remove the competing rewrite that could bypass that handler.
- [x] Verify the exact pytest collection count: **10 test functions** (six
  auth, two settings, two health). The older documentation's 11 named behavior
  scenarios are coverage topics/assertion groups inside those ten functions,
  not 11 pytest tests.
- [x] Run all 10 backend tests against Compose PostgreSQL and Redis in
  `APP_ENV=ci` mode: **10 passed** in both the host run and Python 3.12 Docker
  test-runner run. In this mode, the client fixture uses the migrated
  PostgreSQL database and live Redis with no SQLite or FakeRedis overrides.
- [x] Verify registration, normalized login, logout, `/me` session handling,
  login and registration throttling, Redis fail-closed handling, and service
  readiness through the real-service test run.
- [x] Run backend Ruff and compile checks locally: passed.
- [x] Run frontend TypeScript, ESLint, and optimized production build locally:
  passed. Playwright discovery lists **4 browser tests**.
- [x] Run the four Playwright tests against the running Compose frontend and
  backend using the matching Playwright 1.56.1 browser container: **4 passed**.
  This covers registration, refresh/session persistence, login, protected
  redirects, logout, and a 429 with a valid Redis `Retry-After` through the
  Next.js proxy.
- [x] Verify the Next.js-to-FastAPI proxy through the Compose network; browser
  registration/login/logout and `/me` all passed against the Compose API.
- [x] Verify PostgreSQL persistence across a container restart: registered
  `milestone1-persistence-verification-20261101@example.com` had row ID 14
  before and after `docker compose restart postgres`; post-restart health and
  proxy login/session/logout also passed.
- [x] Inspect Compose logs. Found and fixed two backend image issues (Alembic
  config/migration files were missing from the image; PyJWT was missing from
  the runtime lock). Rebuilt images and confirmed normal startup, migration,
  API traffic, and no remaining app tracebacks.
- [ ] Run the service-backed pytest suite on GitHub Actions. That is where
  `APP_ENV=ci` disables database/Redis test doubles and uses the actual
  PostgreSQL and Redis service containers after `alembic upgrade head`.
- [ ] Observe a passing Actions run, including the real PostgreSQL migration,
  auth CRUD/session tests, login and registration Redis rate-limit tests,
  readiness checks, and browser
  integration tests. No repository remote or `gh` CLI is available in this
  checkout, so this run cannot be triggered or evidenced here.
- [x] Run a full Docker Compose startup, migration, health, auth, frontend
  proxy, browser, and PostgreSQL persistence smoke test. Docker Compose is
  verified for this run.

### Engineering and ML review

- [x] Trace registration/login/logout/me across React forms, Next.js proxy,
  FastAPI contracts/services, and SQLAlchemy persistence.
- [x] Inspect the proxy contract and verify frontend static/build checks; added
  Playwright coverage to exercise requests through that handler.
- [x] Review auth validation, duplicate accounts, normalized email, cookie
  behavior, login/registration rate limits, readiness, and service-unavailable
  behavior in the ten pytest functions.
- [x] Search application code for TODO/FIXME, mocked API responses, fake
  publications, and fabricated model outputs. None were found; the workspace
  empty state is explicitly a future feature.
- [x] ML leakage/evaluation review: this milestone has no model, training data,
  recommendation output, or metric; no ML result is claimed.
- [x] Review persistence/performance boundaries: email has a unique constraint;
  auth operations are bounded. No load benchmark has been run.
- [x] Record known limitations: rate limits key by normalized email and are not
  combined with a trusted client-IP limit; server-side session revocation is
  not implemented.

### Evidence and status

Observed in this Docker Desktop run: both app images built; Compose PostgreSQL
and Redis became healthy; Alembic reached `0001_users (head)`; the 10-test
backend suite passed against live PostgreSQL/Redis in Python 3.12; all four
Playwright tests passed against the Compose frontend/API; and the PostgreSQL
user row survived a container restart with the same ID. Frontend typecheck,
lint, optimized build, backend Ruff, and compile checks also pass.

The separate hosted GitHub Actions workflow has not been run because this
checkout has no Git remote or `gh` executable. Its execution remains
unobserved; no hosted CI result is claimed. Under the existing checklist gate,
Milestone 1 remains **pending that hosted run**. Milestone 2 remains
**in progress at the user's direction**; no later milestone has started.

## Milestone 2 — OpenAlex ingestion and semantic search (in progress)

- [x] Implement the OpenAlex Works client using current bearer-key
  authentication, contact User-Agent, `per_page <= 100`, cursor pagination,
  Retry-After/backoff, and bounded retries. Credentials are read from
  `OPENALEX_API_KEY` and `OPENALEX_MAILTO`; request URLs do not include the key.
- [x] Add durable ingestion jobs with filter-derived idempotency keys,
  run/status/error timestamps, cursor and within-page offset, counters, and
  page-atomic publication/checkpoint commits. A limited run resumes correctly;
  completed runs can safely refresh.
- [x] Add Alembic migrations `0002_openalex_search`,
  `0003_ingestion_offset_index`, and `0004_embedding_source_hash` for
  publications, ingestion jobs, nullable source fields, raw provenance,
  pgvector extension/vectors, full-text GIN and vector HNSW indexes, and
  normalized input hashes. Compose PostgreSQL and a separate PostgreSQL test
  database are migrated to `0004_embedding_source_hash (head)`.
- [x] Add defensive OpenAlex metadata normalization and unique-ID upserts.
  Tests verify malformed/missing fields, `NULL` versus citation count `0`,
  provenance, repeated upserts, pagination offsets, retry-after, failure
  checkpoint recovery, and full refresh without duplicate records.
- [x] Add batched, resumable/cached FastEmbed generation with persisted
  model/version, dimension, content hash, status, attempts, error, vector, and
  generated timestamp. Publications store normalized input hashes; joined
  candidate selection avoids full-corpus scans and per-publication embedding
  lookups. Missing text remains skipped; changed source text can subsequently
  be embedded.
- [x] Load the real FastEmbed 0.9.1
  `sentence-transformers/all-MiniLM-L6-v2` model. Observed a finite 384-value
  vector from test-only text; generated and persisted a real model vector in
  PostgreSQL, then retrieved its explicitly labeled test fixture using the
  pgvector semantic path. Test fixture is not OpenAlex source data.
- [x] Implement lexical PostgreSQL full-text search and semantic pgvector
  cosine search; return actual publication fields, method, explanation, score,
  without reporting latency or relevance metrics before a labelled evaluation
  set exists. A live PostgreSQL-backed semantic API request returned the
  temporary test fixture; the fixture was deleted afterward.
- [x] Add the Next.js search interface and expose it through the existing
  same-origin proxy. The first browser run found that proxy dropped query
  parameters; fixed and verified it. Frontend typecheck, lint, optimized build,
  and all **5 Playwright tests passed**, including search through the proxy.
- [x] Add deterministic fixture tests; local SQLite run: **18 passed, 1
  skipped** (the skipped case requires PostgreSQL). Service-backed run on the
  separate PostgreSQL test database and Redis DB 15: **19 passed** after the
  added checkpoint/missing-text cases. These fixture records are not reported
  as actual OpenAlex data.
- [x] Document model/input provenance and evaluation limits. No retrieval
  latency, relevance metrics, or model-quality claims are reported without a
  valid labelled evaluation set.
- [ ] Run the documented real OpenAlex smoke ingestion, inspect persisted
  source IDs/metadata, then run the real embedding CLI and search those source
  records. No OpenAlex API key or contact address is configured in this
  environment; this gate remains open and no live OpenAlex data is claimed.

### Milestone 2 evidence and status

Observed locally on 2026-11-01: Compose PostgreSQL and the separate PostgreSQL
test database are at `0004_embedding_source_hash (head)`; `/health/ready`
returned PostgreSQL and Redis reachable; both application images rebuilt and
started; frontend typecheck/lint/production build passed; all five Playwright
scenarios passed through Next.js and FastAPI; and the final service-backed
backend suite passed **19 tests** against real PostgreSQL plus real Redis DB
15. The real FastEmbed model returned 384 finite values and generated and
retrieved a temporary test-only fixture through pgvector. This is model and
storage evidence, not a real OpenAlex-data smoke test. No latency or relevance
metric is available without labelled judgments.

Milestone 2 remains **in progress** until the configured real-data smoke gate is
run and inspected. Milestone 1's hosted GitHub Actions evidence also remains
unobserved from the prior checklist; no hosted run is claimed. Milestone 3 has
not started.
