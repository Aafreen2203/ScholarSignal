from redis.exceptions import ConnectionError as RedisConnectionError

from backend.app.core.redis import get_redis_client
from backend.app.main import app


def test_registration_login_me_and_logout(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Researcher@Example.com",
            "password": "a sufficiently long passphrase",
            "display_name": "Researcher",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "researcher@example.com"
    assert "password" not in response.json()
    assert "httponly" in response.headers["set-cookie"].lower()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Researcher"

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "RESEARCHER@example.com",
            "password": "a sufficiently long passphrase",
        },
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_auth_rejects_duplicates_wrong_password_and_invalid_registration(client):
    payload = {
        "email": "reader@example.com",
        "password": "a sufficiently long passphrase",
        "display_name": "Reader",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": payload["email"], "password": "wrong password"}
        ).status_code
        == 401
    )
    invalid = {**payload, "email": "not-an-email", "password": "short"}
    assert client.post("/api/v1/auth/register", json=invalid).status_code == 422


def test_me_requires_valid_session(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("access_token", "not-a-jwt")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_is_rate_limited_per_normalized_email(client):
    payload = {"email": "reader@example.com", "password": "wrong passphrase"}
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    limited = client.post("/api/v1/auth/login", json={**payload, "email": "READER@example.com"})
    assert limited.status_code == 429
    retry_after = int(limited.headers["retry-after"])
    assert 0 < retry_after <= 900


def test_registration_is_rate_limited_per_normalized_email(client):
    payload = {
        "email": "writer@example.com",
        "password": "a sufficiently long passphrase",
        "display_name": "Writer",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    for _ in range(4):
        assert client.post("/api/v1/auth/register", json=payload).status_code == 409
    limited = client.post(
        "/api/v1/auth/register",
        json={**payload, "email": "WRITER@example.com"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_auth_fails_closed_when_redis_is_unavailable(client):
    class BrokenRedis:
        def pipeline(self, transaction=True):
            raise RedisConnectionError("connection refused")

    app.dependency_overrides[get_redis_client] = BrokenRedis
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "reader@example.com",
            "password": "a sufficiently long passphrase",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service is temporarily unavailable"
