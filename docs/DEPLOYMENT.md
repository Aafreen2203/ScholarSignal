# Local run and deployment notes

## Docker Compose local run

Requirements: Docker Engine with Compose v2. Create `.env` from `.env.example`;
set a random `JWT_SECRET` with at least 32 characters and a strong, URL-safe
`POSTGRES_PASSWORD`. Keep both local and untracked. For HTTP localhost,
`COOKIE_SECURE=false` is appropriate.

```bash
cp .env.example .env
# Edit .env without pasting credentials into source files or chat.
make up
docker compose ps
curl -fsS http://localhost:8000/health/ready
```

Frontend: `http://localhost:3000`; API docs: `http://localhost:8000/api/docs`.
Compose runs Next.js in development mode, binding to `0.0.0.0:3001` inside the
container and publishing it on host port 3000. Source files are mounted for
live reload. Use `localhost` or a development-port forward that supports
WebSocket upgrades in the browser; an internal/container IP reached through an
HTTP-only proxy will load pages but cannot carry the HMR WebSocket. The backend
container applies Alembic migrations through the current head before starting
FastAPI. PostgreSQL data and FastEmbed's model cache use named volumes. Do not
use `docker compose down -v` for routine cleanup: that removes the database and
model cache volumes. `docker compose down` leaves them in place.

For a host-run frontend instead of the Compose frontend, use
`cd frontend && npm run dev`; it binds to `0.0.0.0:3001`. Open it at
`http://localhost:3001`. Do not run both frontend dev servers on host port
3001 at the same time.

Useful checks:

```bash
docker compose logs --tail=100 backend frontend postgres redis
docker compose exec backend alembic current
docker compose exec backend python -m backend.app.evaluate_cli
```

Ingestion is not automatic. Any live OpenAlex use must be deliberate: check the
persistent ledger first, keep the $0.10 UTC-day project ceiling, and use a
bounded approved command. Do not resume the saved cursor implicitly. Local
embedding and search inference uses the persistent FastEmbed cache; no paid
embedding service is configured.

## Tests and checks

With Python development dependencies and frontend packages installed:

```bash
pytest -q backend/tests
ruff check backend
python -m compileall -q backend
cd frontend
npm ci
npm run typecheck
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

The backend integration fixture uses real PostgreSQL and Redis when
`APP_ENV=ci`, after `alembic upgrade head`; its CI workflow supplies service
containers. Do not point that cleanup-enabled fixture at a personal database
or Redis DB. The Playwright suite can use the Compose runtime or the hosted
workflow's disposable services. One real-corpus detail/related-paper browser
test skips when no publications were ingested; the other user flows use actual
database persistence.

## Backup and recovery

The Compose PostgreSQL named volume persists through container replacement, but
it is not a backup. For a local logical backup, write outside the repository
and protect the resulting file because it contains accounts, private notes,
collections, and search history:

```bash
docker compose exec -T postgres pg_dump -U scholarsignal scholarsignal > /safe/path/scholarsignal-backup.sql
```

To verify recovery, restore into a separate, newly created test database and
check its Alembic revision and row counts. Do not restore over the active
database as a routine test. No automated backup schedule or point-in-time
recovery setup is configured.

## Production status

This repository has only been verified as a local Compose app. It is not
deployed or load-tested. Before production, configure a managed/private
PostgreSQL deployment with TLS and tested backups; isolate Redis; set secrets
through the deployment secret store; set `COOKIE_SECURE=true`; configure trusted
proxy/IP rate limiting, JWT revocation/rotation policy, monitoring, retention,
and a reviewed migration/rollback process. GitHub Actions is configured but a
hosted run has not been observed in this checkout. No background worker or
scheduled ingestion service is deployed.
