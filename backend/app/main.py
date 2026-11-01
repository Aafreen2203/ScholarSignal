import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.auth import router as auth_router
from backend.app.api.search import router as search_router
from backend.app.api.workspace import router as workspace_router
from backend.app.core.config import get_settings
from backend.app.core.redis import get_redis_client
from backend.app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()
app = FastAPI(title="ScholarSignal API", version="0.1.0", docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        get_redis_client().ping()
    except (SQLAlchemyError, RedisError):
        raise HTTPException(status_code=503, detail="A required service is unavailable") from None
    return {"status": "ready", "database": "reachable", "redis": "reachable"}
