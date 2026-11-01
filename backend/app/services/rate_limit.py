import hashlib
import logging

from redis import Redis, RedisError

from backend.app.services.auth import normalize_email

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class RateLimitUnavailable(Exception):
    pass


def enforce_auth_rate_limit(redis: Redis, *, action: str, email: str) -> None:
    """Enforce a fixed-window identity limit atomically using Redis."""
    limits = {"login": (10, 15 * 60), "register": (5, 60 * 60)}
    if action not in limits:
        raise ValueError("Unknown authentication action")
    maximum, window_seconds = limits[action]
    identity = hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()
    key = f"scholarsignal:rate:{action}:{identity}"
    try:
        pipeline = redis.pipeline(transaction=True)
        pipeline.incr(key)
        pipeline.expire(key, window_seconds, nx=True)
        count, _ = pipeline.execute()
        if int(count) > maximum:
            ttl = max(int(redis.ttl(key)), 1)
            raise RateLimitExceeded(ttl)
    except RateLimitExceeded:
        raise
    except RedisError as exc:
        logger.exception("Redis authentication rate limiter is unavailable")
        raise RateLimitUnavailable from exc
