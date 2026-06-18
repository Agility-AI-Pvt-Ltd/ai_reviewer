import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_idea_lab_session
from app.core.dependencies import enforce_api_rate_limit
from app.schemas.report import (
    ReviewAuthRequiredResponse,
    ReviewJobListResponse,
    ReviewJobQueuedResponse,
    ReviewJobStatusOut,
    ReviewRequest,
    ReviewStartResponse,
    ReviewStateSnapshotOut,
)
from app.services.github_oauth import (
    build_github_oauth_url,
    create_github_oauth_state,
    find_latest_github_credential,
    get_github_access_token,
    github_auth_identity,
    github_oauth_configured,
    github_repository_accessible,
)
from app.services.idea_lab import get_idea_lab_report
from app.services.review_queue import (
    enqueue_review_job,
    get_job_status,
    get_latest_conversation_job_status,
    is_missing_queue_table_error,
    list_review_jobs,
)
from app.services.review_state import list_review_state_snapshots

router = APIRouter(prefix="/review", tags=["review"])


async def _auth_required_response(
    session: AsyncSession,
    *,
    auth_identity: str,
    payload: ReviewRequest,
) -> ReviewAuthRequiredResponse:
    if not github_oauth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is enabled but client id, client secret, or callback URL is missing.",
        )
    oauth_state = await create_github_oauth_state(
        session,
        auth_identity=auth_identity,
        conversation_id=payload.conversation_id,
        github_url=str(payload.github_url),
    )
    return ReviewAuthRequiredResponse(
        conversation_id=payload.conversation_id,
        github_url=payload.github_url,
        oauth_url=build_github_oauth_url(oauth_state.state),
        state=oauth_state.state,
    )


async def _enqueue_response(
    session: AsyncSession,
    *,
    payload: ReviewRequest,
    github_credential_id: int | None = None,
    auth_identity: str | None = None,
) -> ReviewJobQueuedResponse:
    queued_event = await enqueue_review_job(
        session,
        conversation_id=payload.conversation_id,
        github_url=str(payload.github_url),
        github_credential_id=github_credential_id,
        auth_identity=auth_identity,
    )
    return ReviewJobQueuedResponse(
        job_id=queued_event.job_id,
        conversation_id=payload.conversation_id,
        github_url=payload.github_url,
        status_url=f"/review/jobs/{queued_event.job_id}",
    )


@router.post("/start", response_model=ReviewStartResponse)
@router.post("", response_model=ReviewStartResponse)
async def review_project(
    payload: ReviewRequest,
    response: Response,
    auth_payload: dict = Depends(enforce_api_rate_limit),
    idea_lab_session: AsyncSession = Depends(get_idea_lab_session),
) -> ReviewStartResponse:
    await get_idea_lab_report(idea_lab_session, payload.conversation_id)
    try:
        auth_identity = github_auth_identity(auth_payload)
        github_credential_id = None
        if settings.github_oauth_enabled:
            public_accessible = await github_repository_accessible(str(payload.github_url))
            if not public_accessible:
                credential = await find_latest_github_credential(
                    idea_lab_session,
                    auth_identity=auth_identity,
                )
                if credential is not None:
                    try:
                        token = await get_github_access_token(idea_lab_session, credential.id)
                        if await github_repository_accessible(str(payload.github_url), token):
                            github_credential_id = credential.id
                        else:
                            credential = None
                    except ValueError:
                        credential = None
                if credential is None:
                    response.status_code = status.HTTP_200_OK
                    return await _auth_required_response(
                        idea_lab_session,
                        auth_identity=auth_identity,
                        payload=payload,
                    )
        response.status_code = status.HTTP_202_ACCEPTED
        return await _enqueue_response(
            idea_lab_session,
            payload=payload,
            github_credential_id=github_credential_id,
            auth_identity=auth_identity,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub access check failed.",
        ) from exc
    except Exception as exc:
        if is_missing_queue_table_error(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Review queue table is missing. Run db/schema.sql before starting the service.',
            ) from exc
        raise


@router.get("/jobs", response_model=ReviewJobListResponse)
async def review_jobs(
    limit: int = 50,
    conversation_id: str | None = None,
    _: dict = Depends(enforce_api_rate_limit),
    session: AsyncSession = Depends(get_idea_lab_session),
) -> ReviewJobListResponse:
    bounded_limit = max(1, min(limit, 100))
    jobs = await list_review_jobs(
        session,
        limit=bounded_limit,
        conversation_id=conversation_id,
    )
    return ReviewJobListResponse(
        jobs=[ReviewJobStatusOut.model_validate(job) for job in jobs]
    )


@router.get("/jobs/{job_id}", response_model=ReviewJobStatusOut)
async def review_job_status(
    job_id: str,
    _: dict = Depends(enforce_api_rate_limit),
    session: AsyncSession = Depends(get_idea_lab_session),
) -> ReviewJobStatusOut:
    return ReviewJobStatusOut.model_validate(await get_job_status(session, job_id))


@router.get("/{conversation_id}/job", response_model=ReviewJobStatusOut)
async def latest_review_job_status(
    conversation_id: str,
    _: dict = Depends(enforce_api_rate_limit),
    session: AsyncSession = Depends(get_idea_lab_session),
) -> ReviewJobStatusOut:
    return ReviewJobStatusOut.model_validate(
        await get_latest_conversation_job_status(session, conversation_id)
    )


@router.get("/{conversation_id}/state", response_model=list[ReviewStateSnapshotOut])
async def review_state(
    conversation_id: str,
    _: dict = Depends(enforce_api_rate_limit),
    session: AsyncSession = Depends(get_idea_lab_session),
) -> list[ReviewStateSnapshotOut]:
    snapshots = await list_review_state_snapshots(session, conversation_id)
    return [ReviewStateSnapshotOut.model_validate(snapshot) for snapshot in snapshots]
