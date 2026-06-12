import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_chain_of_thought(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return [{"step": 1, "text": str(value)}]

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"step": index, "text": str(item)})
    return normalized


class FeasibilityReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: str
    chain_of_thought: list[dict[str, Any]] | None = None
    idea_fit: str | None = None
    competitors: str | None = None
    opportunity: str | None = None
    score: str | None = None
    targeting: str | None = None
    next_step: str | None = None
    created_at: dt.datetime | None = None

    @field_validator("chain_of_thought", mode="before")
    @classmethod
    def normalize_chain_of_thought(cls, value: Any) -> list[dict[str, Any]] | None:
        return _normalize_chain_of_thought(value)


class IdeaLabReport(BaseModel):
    conversation_id: str
    chain_of_thought: list[dict[str, Any]] | None = None
    idea_fit: str | None = None
    competitors: str | None = None
    opportunity: str | None = None
    score: str | None = None
    targeting: str | None = None
    next_step: str | None = None

    @field_validator("chain_of_thought", mode="before")
    @classmethod
    def normalize_chain_of_thought(cls, value: Any) -> list[dict[str, Any]] | None:
        return _normalize_chain_of_thought(value)

    @classmethod
    def from_orm_report(cls, report: object) -> "IdeaLabReport":
        return cls.model_validate(FeasibilityReportOut.model_validate(report).model_dump())
