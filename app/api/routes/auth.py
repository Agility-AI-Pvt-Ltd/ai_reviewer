from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_idea_lab_session
from app.core.dependencies import enforce_api_rate_limit
from app.schemas.report import ReviewJobQueuedResponse
from app.schemas.auth import AuthVerifyResponse
from app.services.github_oauth import (
    consume_github_oauth_state,
    exchange_github_code,
    fetch_github_user,
    github_repository_accessible,
    store_github_credential,
)
from app.services.review_queue import enqueue_review_job

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/verify", response_model=AuthVerifyResponse)
async def verify_auth(auth_payload: dict[str, Any] = Depends(enforce_api_rate_limit)) -> dict[str, Any]:
    return {"ok": True, "auth": auth_payload}


@router.get("/github/callback", response_model=ReviewJobQueuedResponse)
async def github_callback(
    response: Response,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    session: AsyncSession = Depends(get_idea_lab_session),
) -> ReviewJobQueuedResponse:
    oauth_state = await consume_github_oauth_state(session, state)
    try:
        token_payload = await exchange_github_code(code)
        access_token = str(token_payload["access_token"])
        try:
            github_user = await fetch_github_user(access_token)
        except httpx.HTTPError:
            github_user = None

        if not await github_repository_accessible(oauth_state.github_url, access_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="GitHub authorization did not grant access to the requested repository.",
            )

        credential = await store_github_credential(
            session,
            auth_identity=oauth_state.auth_identity,
            token_payload=token_payload,
            github_user=github_user,
        )
        queued_event = await enqueue_review_job(
            session,
            conversation_id=oauth_state.conversation_id,
            github_url=oauth_state.github_url,
            github_credential_id=credential.id,
            auth_identity=oauth_state.auth_identity,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub OAuth callback failed.",
        ) from exc

    response.status_code = status.HTTP_202_ACCEPTED
    return ReviewJobQueuedResponse(
        job_id=queued_event.job_id,
        conversation_id=queued_event.conversation_id,
        github_url=queued_event.github_url,
        status_url=f"/review/jobs/{queued_event.job_id}",
    )

