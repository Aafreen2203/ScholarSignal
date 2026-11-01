# Local deployment

Requirements: Docker Engine with Compose v2. Copy `.env.example` to `.env`, set
`JWT_SECRET` to a random value of at least 32 characters and choose a strong,
URL-safe `POSTGRES_PASSWORD`, then run `make up`. For direct local startup,
keep the password in `DATABASE_URL` aligned with `POSTGRES_PASSWORD`.
The Compose stack exposes the frontend at `http://localhost:3000`, API at
`http://localhost:8000`, and API docs at `http://localhost:8000/api/docs`.
The API container applies Alembic migrations before serving. PostgreSQL data is
stored in a named volume. `COOKIE_SECURE=false` is only for local HTTP; use HTTPS
and set it true in production.

Without Docker, install Python dependencies with `pip install -r requirements-dev.txt`,
start PostgreSQL and Redis, copy/configure `.env`, run `alembic upgrade head`, then start
the API with `uvicorn backend.app.main:app --reload`. Install frontend
dependencies using `cd frontend && npm ci`, then run `npm run dev`.

