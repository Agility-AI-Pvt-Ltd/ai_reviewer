from types import SimpleNamespace

import pytest

from app.schemas.idea_lab import IdeaLabReport
from app.schemas.report import Alignment, Architecture, ProjectReviewReport, Scores
from app.services import review_worker


def _report() -> ProjectReviewReport:
    return ProjectReviewReport(
        scores=Scores(
            overall=8,
            alignment_with_idea=8,
            architecture_quality=7,
            feature_completeness=8,
            code_organization=8,
        ),
        architecture=Architecture(
            pattern="REST API",
            description="The project exposes a clear API surface.",
            strengths=["Simple routing"],
            weaknesses=["Limited tests"],
        ),
        alignment=Alignment(
            alignment_percentage=80,
            implemented_features=["Review endpoint"],
            missing_features=["Dashboard"],
            extra_features=[],
        ),
        gaps=[],
        improvements=[],
        summary="The project is well aligned with the idea and needs more coverage.",
    )


@pytest.mark.asyncio
async def test_review_worker_cleans_cloned_repo_after_completed_event(monkeypatch, client):
    queued_event = SimpleNamespace(
        id=11,
        job_id="job-cleanup",
        conversation_id="conv-cleanup",
        github_url="https://github.com/example/project",
    )
    events: list[str] = []
    cleanup_calls: list[tuple[str, str]] = []

    async def fake_find_next_queued_job(session, *, stale_after_seconds):
        return queued_event

    async def fake_insert_review_job_event(session, **kwargs):
        events.append(kwargs["event_type"])
        return SimpleNamespace(**kwargs)

    async def fake_get_idea_lab_report(session, conversation_id):
        return IdeaLabReport(conversation_id=conversation_id, idea_fit="Build a review API")

    async def fake_run_review_pipeline(github_url, idea_lab_report, session, job_id=None):
        return _report()

    def fake_cleanup_cloned_repository(github_url, projects_dir):
        cleanup_calls.append((github_url, projects_dir))
        return True

    monkeypatch.setattr(review_worker, "find_next_queued_job", fake_find_next_queued_job)
    monkeypatch.setattr(review_worker, "insert_review_job_event", fake_insert_review_job_event)
    monkeypatch.setattr(review_worker, "get_idea_lab_report", fake_get_idea_lab_report)
    monkeypatch.setattr(review_worker, "run_review_pipeline", fake_run_review_pipeline)
    monkeypatch.setattr(review_worker, "cleanup_cloned_repository", fake_cleanup_cloned_repository)

    did_work = await review_worker.ReviewQueueWorker()._run_once()

    assert did_work is True
    assert events[-1] == "completed"
    assert cleanup_calls == [("https://github.com/example/project", review_worker.settings.projects_dir)]


@pytest.mark.asyncio
async def test_review_worker_recovers_latest_github_token_from_auth_identity(monkeypatch, client):
    queued_event = SimpleNamespace(
        id=12,
        job_id="job-private",
        conversation_id="conv-private",
        github_url="https://github.com/example/private",
        payload={"auth_identity": "user-123"},
    )
    pipeline_kwargs: dict = {}

    async def fake_find_next_queued_job(session, *, stale_after_seconds):
        return queued_event

    async def fake_insert_review_job_event(session, **kwargs):
        return SimpleNamespace(**kwargs)

    async def fake_get_idea_lab_report(session, conversation_id):
        return IdeaLabReport(conversation_id=conversation_id, idea_fit="Build a review API")

    async def fake_find_latest_github_credential(session, *, auth_identity):
        assert auth_identity == "user-123"
        return SimpleNamespace(id=99)

    async def fake_get_github_access_token(session, credential_id):
        assert credential_id == 99
        return "gho_private_token"

    async def fake_github_repository_accessible(github_url, access_token=None):
        assert github_url == "https://github.com/example/private"
        assert access_token == "gho_private_token"
        return True

    async def fake_run_review_pipeline(github_url, idea_lab_report, session, **kwargs):
        pipeline_kwargs.update(kwargs)
        return _report()

    def fake_cleanup_cloned_repository(github_url, projects_dir):
        return True

    monkeypatch.setattr(review_worker, "find_next_queued_job", fake_find_next_queued_job)
    monkeypatch.setattr(review_worker, "insert_review_job_event", fake_insert_review_job_event)
    monkeypatch.setattr(review_worker, "get_idea_lab_report", fake_get_idea_lab_report)
    monkeypatch.setattr(
        review_worker,
        "find_latest_github_credential",
        fake_find_latest_github_credential,
    )
    monkeypatch.setattr(review_worker, "get_github_access_token", fake_get_github_access_token)
    monkeypatch.setattr(
        review_worker,
        "github_repository_accessible",
        fake_github_repository_accessible,
    )
    monkeypatch.setattr(review_worker, "run_review_pipeline", fake_run_review_pipeline)
    monkeypatch.setattr(review_worker, "cleanup_cloned_repository", fake_cleanup_cloned_repository)

    did_work = await review_worker.ReviewQueueWorker()._run_once()

    assert did_work is True
    assert pipeline_kwargs["github_access_token"] == "gho_private_token"
