from typing import Any

from pydantic import BaseModel


class AuthVerifyResponse(BaseModel):
    ok: bool
    auth: dict[str, Any]
