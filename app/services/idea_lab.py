from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idea_lab import FeasibilityReport
from app.schemas.idea_lab import IdeaLabReport


async def get_idea_lab_report(session: AsyncSession, conversation_id: str) -> IdeaLabReport:
    result = await session.execute(
        select(FeasibilityReport).where(FeasibilityReport.conversation_id == conversation_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idea Lab feasibility report not found",
        )
    return IdeaLabReport.from_orm_report(report)
