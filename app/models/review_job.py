import datetime as dt
from typing import Any, Literal

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import get_ist_now

ReviewJobEventType = Literal[
    "queued",
    "started",
    "idea_lab_loading",
    "idea_lab_loaded",
    "review_prepared",
    "graph_extract_started",
    "graph_extract_completed",
    "graph_summary_ready",
    "evaluation_started",
    "evaluation_completed",
    "report_persisted",
    "completed",
    "failed",
]


class ReviewJobEvent(Base):
    """
    Append-only Postgres-backed review queue.
    A job is the event stream for one job_id; workers insert events instead of
    updating rows, so the history remains durable and auditable.
    """

    __tablename__ = "review_job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=get_ist_now, nullable=False)
