import logging
from typing import Any

import jwt
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


def _resolve_internal_auth_key() -> str:
    algorithm = settings.internal_auth_algorithm.upper()
    if algorithm.startswith("RS"):
        key = (settings.internal_auth_jwt_public_key or "").strip()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Internal auth public key is not configured.",
            )
        return key.replace("\\n", "\n")

    key = (settings.internal_auth_jwt_secret or settings.jwt_secret or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal auth secret is not configured.",
        )
    return key


def verify_internal_service_token(token: str) -> dict[str, Any]:
    decode_kwargs: dict[str, Any] = {
        "algorithms": [settings.internal_auth_algorithm],
    }
    if settings.internal_auth_issuer:
        decode_kwargs["issuer"] = settings.internal_auth_issuer
    if settings.internal_auth_audience:
        decode_kwargs["audience"] = settings.internal_auth_audience

    try:
        payload = jwt.decode(token, _resolve_internal_auth_key(), **decode_kwargs)
    except jwt.PyJWTError as exc:
        logger.warning("internal_auth.invalid_jwt: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    required_service = (settings.internal_auth_required_service or "").strip()
    if required_service and payload.get("service") != required_service:
        logger.warning(
            "internal_auth.invalid_service_claim service=%s required=%s",
            payload.get("service"),
            required_service,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
