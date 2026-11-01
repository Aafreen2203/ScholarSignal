# Current limitations

- Milestone 2 implements the ingestion and search foundation, but the small
  real-data OpenAlex smoke run is pending operator-supplied API credentials.
  No recommendation, graph, or experiment system is implemented.
- Ingestion and embedding generation run as explicit CLI tasks; scheduling and
  background worker orchestration are not configured.
- The session is a signed bearer token in an HttpOnly cookie. Logout clears the
  browser cookie; token revocation/rotation and IP-level rate limits are future
  security work before production exposure. Login and registration limits are
  Redis-backed per normalized email. A distributed attacker can consume the
  same account's limit, so production abuse controls should combine account and
  trusted client-network signals.
- Production settings reject the development JWT secret and insecure cookies,
  but deployment secrets and HTTPS termination still require operator setup.
- Account endpoints have not been load-tested or deployed. Docker Compose
  startup, health checks, PostgreSQL migrations, and persistence across a
  PostgreSQL container restart were verified locally on 2026-11-01.
- The original ten-test suite passed against real Compose PostgreSQL and Redis
  in `APP_ENV=ci` mode (Python 3.12); Milestone 2 adds deterministic fixture
  tests that also run with SQLite locally and PostgreSQL/Redis in CI mode.
- Four Milestone 1 Playwright tests passed against the Compose frontend and API
  through the Next.js proxy using Playwright 1.56.1. The separate
  GitHub Actions workflow remains unobserved because this checkout has no
  remote or `gh` executable.
- Semantic search has an actual 384-dimensional FastEmbed/ONNX model and
  PostgreSQL pgvector integration. No labelled relevance dataset exists, so
  latency and relevance metrics are not reported.
- Automated tests use FastAPI's TestClient; the installed Starlette/httpx
  combination emits a deprecation warning even though tests pass.
- Google Fonts are loaded from the network by the UI; offline deployments use
  system fallback fonts.

