from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_idea_lab_session
from app.core.dependencies import enforce_api_rate_limit
from app.schemas.report import (
    ReviewJobListResponse,
    ReviewJobQueuedResponse,
    ReviewJobStatusOut,
    ReviewRequest,
    ReviewStateSnapshotOut,
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


@router.post("", response_model=ReviewJobQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
async def review_project(
    payload: ReviewRequest,
    _: dict = Depends(enforce_api_rate_limit),
    idea_lab_session: AsyncSession = Depends(get_idea_lab_session),
) -> ReviewJobQueuedResponse:
    await get_idea_lab_report(idea_lab_session, payload.conversation_id)
    try:
        queued_event = await enqueue_review_job(
            idea_lab_session,
            conversation_id=payload.conversation_id,
            github_url=str(payload.github_url),
        )
    except Exception as exc:
        if is_missing_queue_table_error(exc):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Review queue table is missing. Run db/schema.sql before starting the service.',
            ) from exc
        raise
    return ReviewJobQueuedResponse(
        job_id=queued_event.job_id,
        conversation_id=payload.conversation_id,
        github_url=payload.github_url,
        status_url=f"/review/jobs/{queued_event.job_id}",
    )


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
