import logging
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, Response, WebSocket, status

from app.core.config import settings
from app.core.rate_limiter import check_api_rate_limit, resolve_rate_limit_identity
from app.core.security import verify_internal_service_token

logger = logging.getLogger(__name__)


def require_internal_service_auth(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not settings.internal_auth_enabled:
        return {}

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_internal_service_token(token.strip())


async def enforce_api_rate_limit(
    request: Request,
    response: Response,
    auth_payload: dict[str, Any] = Depends(require_internal_service_auth),
) -> dict[str, Any]:
    if not settings.api_rate_limit_enabled:
        return auth_payload

    if request.method.upper() in {"HEAD", "OPTIONS"}:
        return auth_payload

    limit = max(0, settings.api_rate_limit_requests)
    window_seconds = max(1, settings.api_rate_limit_window_seconds)
    if limit == 0:
        return auth_payload

    identity = resolve_rate_limit_identity(request, auth_payload)
    allowed, retry_after, remaining = await check_api_rate_limit(identity)

    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Window"] = str(window_seconds)

    if allowed:
        return auth_payload

    logger.warning("api_rate_limit.exceeded identity=%s retry_after=%s", identity, retry_after)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"API rate limit exceeded. Max {limit} requests per {window_seconds} seconds.",
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Window": str(window_seconds),
        },
    )


def verify_websocket_internal_auth(websocket: WebSocket) -> dict[str, Any] | None:
    if not settings.internal_auth_enabled:
        return {}

    token = websocket.query_params.get("token")
    if not token:
        return None

    try:
        return verify_internal_service_token(token)
    except HTTPException:
        return None
