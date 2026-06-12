import datetime as dt
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReviewStateSnapshot(Base):
    """
    Append-only pipeline state.
    Runtime code inserts new snapshots instead of updating rows, so production DB
    permissions can stay limited to SELECT and INSERT.
    """

    __tablename__ = "review_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    project_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    idea_lab_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    graph: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    graph_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    review_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, nullable=False)
