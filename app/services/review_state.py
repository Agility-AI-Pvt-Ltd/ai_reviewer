from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review_state import ReviewStateSnapshot
from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import ProjectReviewReport


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


async def insert_review_state_snapshot(
    session: AsyncSession,
    *,
    conversation_id: str,
    github_url: str,
    stage: str,
    state: dict[str, Any] | None = None,
    idea_lab_report: IdeaLabReport | dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    graph_summary: dict[str, Any] | None = None,
    review_report: ProjectReviewReport | dict[str, Any] | None = None,
    project_path: str | None = None,
    error: str | None = None,
) -> ReviewStateSnapshot:
    snapshot = ReviewStateSnapshot(
        conversation_id=conversation_id,
        github_url=github_url,
        stage=stage,
        project_path=project_path,
        state=state or {},
        idea_lab_report=_dump_model(idea_lab_report),
        graph=graph,
        graph_summary=graph_summary,
        review_report=_dump_model(review_report),
        error=error,
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def list_review_state_snapshots(
    session: AsyncSession,
    conversation_id: str,
) -> list[ReviewStateSnapshot]:
    result = await session.execute(
        select(ReviewStateSnapshot)
        .where(ReviewStateSnapshot.conversation_id == conversation_id)
        .order_by(ReviewStateSnapshot.created_at.asc(), ReviewStateSnapshot.id.asc())
    )
    return list(result.scalars().all())
