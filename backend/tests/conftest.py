import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.core.redis import get_redis_client
from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models import User  # noqa: F401


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def incr(self, key):
        self.operations.append(("incr", key))
        return self

    def expire(self, key, seconds, nx=False):
        self.operations.append(("expire", key, seconds, nx))
        return self

    def execute(self):
        results = []
        for operation in self.operations:
            if operation[0] == "incr":
                key = operation[1]
                self.redis.values[key] = self.redis.values.get(key, 0) + 1
                results.append(self.redis.values[key])
            else:
                results.append(True)
        return results


class FakeRedis:
    def __init__(self):
        self.values = {}

    def pipeline(self, transaction=True):
        assert transaction
        return FakePipeline(self)

    def ttl(self, key):
        return 900

    def ping(self):
        return True


@pytest.fixture
def client():
    if get_settings().app_env == "ci":
        # CI runs Alembic before pytest. These tests intentionally use the same
        # PostgreSQL and Redis services as the application, with no dependency
        # overrides that could mask integration failures.
        from backend.app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(delete(User))
            session.commit()
        redis = get_redis_client()
        redis.flushdb()
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.clear()
            redis.flushdb()
        return

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    fake_redis = FakeRedis()

    def override_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis_client] = override_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
