import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_job import ReviewJobEvent
from app.core.time import get_ist_now

TERMINAL_EVENTS = {"completed", "failed"}
STATUS_EVENTS = {"queued", "started", "completed", "failed"}


def is_missing_queue_table_error(exc: Exception) -> bool:
    text = str(exc)
    return isinstance(exc, ProgrammingError) and (
        "UndefinedTableError" in text
        or ("review_job_events" in text and "does not exist" in text)
    )


async def insert_review_job_event(
    session: AsyncSession,
    *,
    job_id: str,
    conversation_id: str,
    github_url: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> ReviewJobEvent:
    event = ReviewJobEvent(
        job_id=job_id,
        conversation_id=conversation_id,
        github_url=github_url,
        event_type=event_type,
        payload=payload or {},
        error=error,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def enqueue_review_job(
    session: AsyncSession,
    *,
    conversation_id: str,
    github_url: str,
) -> ReviewJobEvent:
    job_id = str(uuid.uuid4())
    return await insert_review_job_event(
        session,
        job_id=job_id,
        conversation_id=conversation_id,
        github_url=github_url,
        event_type="queued",
        payload={"conversation_id": conversation_id, "github_url": github_url},
    )


async def list_review_job_events(session: AsyncSession, job_id: str) -> list[ReviewJobEvent]:
    result = await session.execute(
        select(ReviewJobEvent)
        .where(ReviewJobEvent.job_id == job_id)
        .order_by(ReviewJobEvent.created_at.asc(), ReviewJobEvent.id.asc())
    )
    return list(result.scalars().all())


async def list_conversation_job_events(
    session: AsyncSession,
    conversation_id: str,
) -> list[ReviewJobEvent]:
    result = await session.execute(
        select(ReviewJobEvent)
        .where(ReviewJobEvent.conversation_id == conversation_id)
        .order_by(ReviewJobEvent.created_at.desc(), ReviewJobEvent.id.desc())
    )
    return list(result.scalars().all())


def summarize_job_events(events: list[ReviewJobEvent]) -> dict[str, Any]:
    if not events:
        return {"status": "not_found", "events": []}

    latest = events[-1]
    queued = events[0]
    status = "queued"
    for event in events:
        if event.event_type in STATUS_EVENTS:
            status = event.event_type

    completed_events = [event for event in events if event.event_type == "completed"]
    report = None
    if completed_events:
        latest_completed_payload = completed_events[-1].payload or {}
        report = latest_completed_payload.get("report")

    return {
        "job_id": latest.job_id,
        "conversation_id": latest.conversation_id,
        "github_url": latest.github_url,
        "status": status,
        "error": latest.error,
        "report": report,
        "queued_at": queued.created_at,
        "updated_at": latest.created_at,
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "payload": event.payload,
                "error": event.error,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


async def get_job_status(session: AsyncSession, job_id: str) -> dict[str, Any]:
    return summarize_job_events(await list_review_job_events(session, job_id))


async def list_review_jobs(
    session: AsyncSession,
    *,
    limit: int = 50,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    query = select(ReviewJobEvent).order_by(
        ReviewJobEvent.created_at.asc(),
        ReviewJobEvent.id.asc(),
    )
    if conversation_id:
        query = query.where(ReviewJobEvent.conversation_id == conversation_id)

    result = await session.execute(query)
    events_by_job: dict[str, list[ReviewJobEvent]] = {}
    for event in result.scalars().all():
        events_by_job.setdefault(event.job_id, []).append(event)

    summaries = [summarize_job_events(events) for events in events_by_job.values()]
    summaries.sort(key=lambda item: item.get("updated_at") or dt.datetime.min, reverse=True)
    return summaries[:limit]


async def get_latest_conversation_job_status(
    session: AsyncSession,
    conversation_id: str,
) -> dict[str, Any]:
    events = await list_conversation_job_events(session, conversation_id)
    if not events:
        return {"status": "not_found", "events": []}

    latest_job_id = events[0].job_id
    return await get_job_status(session, latest_job_id)


async def find_next_queued_job(session: AsyncSession, *, stale_after_seconds: int) -> ReviewJobEvent | None:
    result = await session.execute(
        select(ReviewJobEvent)
        .where(ReviewJobEvent.event_type == "queued")
        .order_by(ReviewJobEvent.created_at.asc(), ReviewJobEvent.id.asc())
        .limit(50)
    )
    queued_events = list(result.scalars().all())
    stale_before = get_ist_now() - dt.timedelta(seconds=stale_after_seconds)

    for queued_event in queued_events:
        events = await list_review_job_events(session, queued_event.job_id)
        event_types = [event.event_type for event in events]
        if any(event_type in TERMINAL_EVENTS for event_type in event_types):
            continue

        started_events = [event for event in events if event.event_type == "started"]
        if not started_events:
            return queued_event

        latest_started = started_events[-1]
        if latest_started.created_at < stale_before:
            return queued_event

    return None
