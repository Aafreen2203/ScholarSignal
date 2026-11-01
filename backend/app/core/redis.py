from functools import lru_cache

from redis import Redis

from backend.app.core.config import get_settings


@lru_cache
def get_redis_client() -> Redis:
    return Redis.from_url(
        get_settings().redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )
