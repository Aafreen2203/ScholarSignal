from redis.exceptions import ConnectionError as RedisConnectionError


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query):
        assert str(query) == "SELECT 1"


class Database:
    def connect(self):
        return Connection()


class ReadyRedis:
    def ping(self):
        return True


def test_liveness_and_readiness(client, monkeypatch):
    monkeypatch.setattr("backend.app.main.engine", Database())
    monkeypatch.setattr("backend.app.main.get_redis_client", ReadyRedis)
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "reachable", "redis": "reachable"}


def test_readiness_returns_service_unavailable_when_redis_is_down(client, monkeypatch):
    monkeypatch.setattr("backend.app.main.engine", Database())

    class BrokenRedis:
        def ping(self):
            raise RedisConnectionError("connection refused")

    monkeypatch.setattr("backend.app.main.get_redis_client", BrokenRedis)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "A required service is unavailable"
