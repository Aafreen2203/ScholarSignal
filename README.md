# ScholarSignal

ScholarSignal is a research discovery platform. The repository contains the
Milestone 1 account foundation and the Milestone 2 OpenAlex ingestion,
publication storage, embedding, and search implementation. Recommendations,
graph learning, and labelled retrieval evaluation are not implemented.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), API contracts in
[docs/API.md](docs/API.md), and the evidence-based status in
[docs/MILESTONE_CHECKLIST.md](docs/MILESTONE_CHECKLIST.md).

## Run locally

With Docker Compose v2:

```bash
cp .env.example .env
# Replace JWT_SECRET with a random secret of at least 32 characters and set a
# strong POSTGRES_PASSWORD (use URL-safe characters in this local Compose setup).
make up
```

Frontend: `http://localhost:3000`. API docs: `http://localhost:8000/api/docs`.
Compose starts PostgreSQL and Redis, runs database migrations, and starts the
frontend and API. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

To ingest a small real OpenAlex sample, configure a verified
`OPENALEX_API_KEY` and your contact address in `OPENALEX_MAILTO`, then run:

```bash
docker compose exec backend python -m backend.app.ingestion.cli works \
  --filter publication_year:2024 --limit 5
docker compose exec backend python -m backend.app.ingestion.cli embeddings
```

The API key is required for cursor paging beyond the first page; the client
honors OpenAlex rate limits. The `/search` page offers lexical and semantic
retrieval. The OpenAlex smoke run still requires operator credentials and is
not claimed as complete here. See [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md).

Docker Compose was verified locally on 2026-11-01: both application images
built, PostgreSQL and Redis became healthy, Alembic reached head, ten backend
tests passed against PostgreSQL/Redis, four Playwright tests passed through the
Next.js proxy, and a PostgreSQL user survived a container restart. The separate
GitHub Actions workflow is configured but has no observed run in this checkout;
see [docs/MILESTONE_CHECKLIST.md](docs/MILESTONE_CHECKLIST.md).

## Development checks

```bash
pip install -r requirements-dev.txt
pytest
ruff check backend
cd frontend && npm ci && npm run typecheck && npm run lint && npm run build
```

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) and
[docs/MILESTONE_CHECKLIST.md](docs/MILESTONE_CHECKLIST.md) for observed status.
The hosted GitHub Actions run for Milestone 1 and real-data OpenAlex smoke are
still separate verification gates.

