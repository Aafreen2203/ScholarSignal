# ScholarSignal

ScholarSignal is a local research discovery platform built around real OpenAlex
publication records. It provides lexical, local semantic, and hybrid search;
paper details and source references; and a private authenticated workspace for
saved papers, collections, notes, recent views, and search history.

The current local database contains five real OpenAlex 2024 records and five
384-dimensional FastEmbed vectors. Synthetic records used by automated tests
are explicitly identified in fixtures and evaluation documentation. The
five-record labeled evaluation is a small, single-annotator pilot, not a
production quality benchmark.

## Stack and architecture

- Frontend: Next.js App Router, React, TypeScript, Tailwind CSS.
- API: FastAPI, Pydantic, SQLAlchemy.
- Persistence: PostgreSQL, pgvector, Alembic; Redis for authentication limits.
- Retrieval: PostgreSQL full text, FastEmbed
  `sentence-transformers/all-MiniLM-L6-v2`, pgvector cosine search, and bounded
  reciprocal-rank fusion.
- Data: OpenAlex cursor ingestion is an explicit operator CLI with a persistent
  usage ledger and a $0.10 per-UTC-day project ceiling.

See [architecture](docs/ARCHITECTURE.md), [API contracts](docs/API.md),
[evaluation](docs/EVALUATION.md), [data pipeline](docs/DATA_PIPELINE.md), and
[the checklist and verification evidence](docs/MILESTONE_CHECKLIST.md).

## Run locally

Requirements: Docker Engine and Compose v2. Create `.env` from the placeholder
template, then set a strong URL-safe `POSTGRES_PASSWORD` and a random `JWT_SECRET`
of at least 32 characters. Do not commit `.env`.

```bash
cp .env.example .env
# Edit .env with local-only values. Do not paste secrets into source control.
make up
```

Open the research discovery app at `http://localhost:3000`; API docs are at
`http://localhost:8000/api/docs`. Compose starts PostgreSQL/Redis, applies
Alembic migrations, and starts the app. The local workspace and five existing
source records remain in Compose's named PostgreSQL volume across container
restarts.

The OpenAlex credentials in `.env` are used only by operator-run ingestion.
Ingestion does not run automatically. The five-record smoke result is already
stored locally. Do not resume its saved cursor or make more OpenAlex requests
unless you intentionally approve and verify the persistent usage ledger first.
Local embeddings and search do not use an external paid API.

## Development checks

```bash
pip install -r requirements-dev.txt
pytest -q backend/tests
ruff check backend
python -m compileall -q backend
cd frontend && npm ci && npm run typecheck && npm run lint && npm run build
```

For browser checks, install Playwright's Chromium (`npx playwright install
chromium`) or use the already configured Playwright 1.56.1 container as shown
in [deployment documentation](docs/DEPLOYMENT.md).

## Current verification boundary

Local Docker Compose has applied migrations through `0007_research_workspace`.
The full backend suite passed against a newly created isolated PostgreSQL
database and isolated Redis DB; the frontend typecheck, lint, and optimized
build passed; and seven Playwright tests passed through the Compose Next.js
proxy against the five stored OpenAlex records. The pilot evaluation results
and their limits are in [docs/EVALUATION.md](docs/EVALUATION.md).

The hosted GitHub Actions result is still unobserved; no hosted pass is claimed.
The app has not been deployed or load-tested and is not represented as
production-ready. See [limitations](docs/LIMITATIONS.md).
