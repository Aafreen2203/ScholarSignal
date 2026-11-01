.PHONY: up down test lint typecheck migrate
up:
	docker compose up --build
down:
	docker compose down
test:
	pytest
lint:
	ruff check backend
typecheck:
	cd frontend && npm run typecheck
migrate:
	alembic upgrade head

