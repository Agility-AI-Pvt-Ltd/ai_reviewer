import datetime as dt
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import get_ist_now


class FeasibilityReport(Base):
    """
    Stores the structured JSON output from the final Feasibility LLM agent node.
    Mirrors the Idea Lab database table in Neon Postgres.
    """

    __tablename__ = "feasibility_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    chain_of_thought: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    idea_fit: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitors: Mapped[str | None] = mapped_column(Text, nullable=True)
    opportunity: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[str | None] = mapped_column(String, nullable=True)
    targeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=get_ist_now)
