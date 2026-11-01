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
Milestone 1 remains **pending that hosted run**. Milestone 2 is now verified
complete; Milestone 3 has not started.

## Milestone 2 — OpenAlex ingestion and semantic search (complete)

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
  normalized input hashes. The separate PostgreSQL test database was verified
  at `0004_embedding_source_hash`; Compose PostgreSQL was subsequently migrated
  through `0006_openalex_usage_events` for the real-data smoke run.
- [x] Add Alembic migrations `0005_openalex_usage` and
  `0006_openalex_usage_events` for persistent account snapshots, the $0.10
  per-UTC-day project ceiling, request reservations/results, and auditable
  manual reconciliation. The original unknown-cost aggregate is preserved.
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
- [x] Run one controlled real-data smoke request on 2026-11-01 using the
  dedicated `smoke` command, `publication_year:2024`, one page, and a five-work
  page size. One `/works` request returned and persisted five records in
  PostgreSQL; the job is paused with its next cursor saved. Actual cost was
  $0.0001 (1 credit), leaving $0.9999 of the account's $1.00 daily budget.
  Project spend is $0.0001 against the $0.10 UTC ceiling.
- [x] Generate embeddings only for the five newly ingested OpenAlex records
  using local FastEmbed `sentence-transformers/all-MiniLM-L6-v2` 0.9.1. Five
  complete vectors are linked to the five expected OpenAlex IDs; each has 384
  finite dimensions. No other publication rows existed and no prior complete
  embeddings were regenerated.
- [x] Verify lexical search through the FastAPI API and Next.js proxy using
  real records, including titles, abstracts, OpenAlex IDs, keyword ranking, and
  an empty-result query. Verify semantic search through FastAPI and the browser
  proxy using local query embeddings and PostgreSQL pgvector; expected real
  OpenAlex records ranked first for protein structure, cancer statistics, and
  indigenous research queries. These checks are functional examples, not a
  labelled relevance evaluation.

### Milestone 2 evidence and status

Observed locally on 2026-11-01: Compose PostgreSQL and the separate PostgreSQL
test database were at `0004_embedding_source_hash`; the Compose database is at
`0006_openalex_usage_events (head)`. The one-page live smoke returned five
records for one request, and the account reported a $0.0001 request cost. All
five real records received a finite 384-dimensional FastEmbed vector. API and
browser-proxy lexical and semantic searches returned the expected records and
fields. The complete local backend suite passed **36 tests, 1 skipped**;
Ruff, compileall, and diff checks passed. A Chromium browser test passed via the
existing Playwright 1.56.1 container. The prior FastEmbed fixture test remains
separately identified as synthetic. No latency or retrieval-quality metric is
reported without labelled judgments.

Milestone 2 is **complete** against its ingestion and search acceptance
criteria. Its live data smoke, real-record embeddings, and lexical/semantic
integration are verified. Milestone 1's hosted GitHub Actions evidence remains
unobserved; no hosted run is claimed.

## Product functionality continuation (post-Milestone 2 foundation)

- [x] Add owner-scoped saved papers, collections, collection membership,
  research notes, recent views, and bounded search history with migration
  `0007_research_workspace`. Isolated PostgreSQL migration reached
  `0007_research_workspace (head)`; the Compose database also reports that
  revision. The existing five publication rows and all five complete vectors
  (384 dimensions) remained present after rebuilding/restarting app services.
- [x] Expose workspace APIs through the Next.js same-origin proxy; verify
  authenticated create/list/delete, collection contents, membership add/remove,
  and notes flows in the browser suite. Seven Playwright tests passed, including registration,
  session persistence, login, protected route, logout, rate-limit response,
  search, paper detail/related records, and workspace CRUD.
- [x] Add paper detail pages with stored OpenAlex metadata, DOI/OpenAlex source
  links, references where present, save actions, and locally computed related
  records. Browser verification used the five persisted real records.
- [x] Add lexical, semantic, and reciprocal-rank hybrid search with bounded
  candidate reporting, metadata/year filtering, pagination, sorting,
  per-result explanations, empty/loading/error states, and search-history
  integration. Calls through `/api/v1/search` on the Next.js proxy returned
  the expected cancer, AlphaFold 3, and Indigenous-methodology records and
  abstracts; the year-filter case also returned the 2024 cancer record.
- [x] Add a documented five-query, five-record single-annotator pilot and
  executable Precision@3, Recall@3, MRR, nDCG@3, and latency evaluation.
  Latest local PostgreSQL/pgvector run recorded lexical 0.2/0.6/0.6/0.6,
  semantic 0.3333/1/1/1, and hybrid 0.3333/1/1/1 for those metrics, with
  mean latencies 10.853/21.385/19.346 ms. This tiny subjective set is not a
  general quality claim or a valid comparison benchmark.
- [x] Run the full backend suite on isolated PostgreSQL and Redis DB 14 after
  applying Alembic migrations: **43 passed**. The host SQLite/default test run
  reported **42 passed, 1 skipped** (the PostgreSQL-only case). Ruff,
  `compileall`, frontend TypeScript, ESLint, and production build passed.
- [x] Rebuild and recreate Compose backend/frontend without resetting data;
  verify PostgreSQL and Redis health, readiness endpoint, migration head,
  record/vector counts, and no traceback/error in the inspected app log tail.
- [x] Run the seven Playwright browser tests against the rebuilt Compose
  frontend and backend using Playwright 1.56.1: **7 passed**.
- [ ] Hosted GitHub Actions run remains unobserved. No remote was available in
  this local checkout; local verification does not substitute for hosted CI.
- [ ] Background ingestion/queue worker, production deployment, independent
  multi-annotator search judgments, larger-corpus load benchmarks, and
  personalized recommendations remain unfinished. Ingestion remains an
  explicit budget-guarded operator CLI and was not run in this continuation.

This continuation did not start Milestone 3 and made no OpenAlex requests.
It preserves the project’s five real OpenAlex records and their existing
embeddings. It does not resolve the outstanding hosted Milestone 1 Actions
gate, so the overall project is not represented as fully verified.
