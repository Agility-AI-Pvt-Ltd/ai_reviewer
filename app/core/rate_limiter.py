import math
import time
from typing import Any

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis

    if not settings.redis_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis URL is required when API rate limiting is enabled.",
        )

    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis

    if _redis is not None:
        await _redis.aclose()
        _redis = None


def resolve_rate_limit_identity(request: Request, auth_payload: dict[str, Any]) -> str:
    service = auth_payload.get("service")
    subject = auth_payload.get("sub")
    if service:
        return f"service:{service}"
    if subject:
        return f"sub:{subject}"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return f"ip:{forwarded_for.split(',')[0].strip()}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


async def check_api_rate_limit(identity: str) -> tuple[bool, int, int]:
    limit = max(0, settings.api_rate_limit_requests)
    window_seconds = max(1, settings.api_rate_limit_window_seconds)
    if limit == 0:
        return True, 0, 0

    now = time.time()
    window_id = math.floor(now / window_seconds)
    retry_after = max(1, int(((window_id + 1) * window_seconds) - now))
    key = f"futurex-reviewer:rate-limit:{identity}:{window_id}"

    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds + 1)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis rate limiter is unavailable.",
        ) from exc

    remaining = max(0, limit - count)
    if count > limit:
        return False, retry_after, remaining
    return True, retry_after, remaining
