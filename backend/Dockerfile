FROM python:3.12-slim
WORKDIR /app
COPY requirements-runtime.lock ./
COPY backend ./backend
COPY alembic.ini ./alembic.ini
COPY backend/migrations ./backend/migrations
RUN pip install --no-cache-dir -r requirements-runtime.lock
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]

