from typing import Any

from fastapi import APIRouter, Depends

from app.core.dependencies import enforce_api_rate_limit
from app.schemas.auth import AuthVerifyResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/verify", response_model=AuthVerifyResponse)
async def verify_auth(auth_payload: dict[str, Any] = Depends(enforce_api_rate_limit)) -> dict[str, Any]:
    return {"ok": True, "auth": auth_payload}


