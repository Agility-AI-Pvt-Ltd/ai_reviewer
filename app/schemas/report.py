import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Scores(BaseModel):
    overall: float = Field(ge=0, le=10)
    alignment_with_idea: float = Field(ge=0, le=10)
    architecture_quality: float = Field(ge=0, le=10)
    feature_completeness: float = Field(ge=0, le=10)
    code_organization: float = Field(ge=0, le=10)


class Architecture(BaseModel):
    pattern: Literal[
        "MVC",
        "Layered",
        "Monolithic",
        "REST API",
        "Component-based",
        "Event-driven",
        "Mixed",
    ]
    description: str
    strengths: list[str]
    weaknesses: list[str]


class Alignment(BaseModel):
    alignment_percentage: float = Field(ge=0, le=100)
    implemented_features: list[str]
    missing_features: list[str]
    extra_features: list[str]


class Gap(BaseModel):
    area: str
    description: str
    severity: Literal["critical", "major", "minor"]


class Improvement(BaseModel):
    title: str
    description: str
    priority: Literal["high", "medium", "low"]


class ProjectReviewReport(BaseModel):
    scores: Scores
    architecture: Architecture
    alignment: Alignment
    gaps: list[Gap]
    improvements: list[Improvement]
    summary: str


class ReviewRequest(BaseModel):
    github_url: HttpUrl
    conversation_id: str = Field(min_length=1)


class ReviewResponse(BaseModel):
    conversation_id: str
    github_url: HttpUrl
    report: ProjectReviewReport


class ReviewJobEventOut(BaseModel):
    id: int
    event_type: str
    payload: dict
    error: str | None = None
    created_at: dt.datetime


class ReviewJobStatusOut(BaseModel):
    job_id: str | None = None
    conversation_id: str | None = None
    github_url: str | None = None
    status: str
    error: str | None = None
    report: dict | None = None
    queued_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None
    events: list[ReviewJobEventOut] = Field(default_factory=list)


class ReviewJobListResponse(BaseModel):
    jobs: list[ReviewJobStatusOut] = Field(default_factory=list)


class ReviewJobQueuedResponse(BaseModel):
    job_id: str
    conversation_id: str
    github_url: HttpUrl
    status: str = "queued"
    status_url: str


class ReviewStateSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: str
    github_url: str
    stage: str
    project_path: str | None = None
    state: dict
    idea_lab_report: dict | None = None
    graphify_graph_json: dict | None = None
    graph: dict | None = None
    graph_summary: dict | None = None
    review_report: dict | None = None
    error: str | None = None
    created_at: dt.datetime
