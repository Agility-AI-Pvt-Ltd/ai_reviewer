import asyncio

import jwt

from app.core import database
from app.core.config import settings
from app.models.idea_lab import FeasibilityReport
from app.services.review_queue import get_job_status, insert_review_job_event


def _configure_internal_auth() -> None:
    settings.internal_auth_enabled = True
    settings.internal_auth_algorithm = "HS256"
    settings.internal_auth_jwt_secret = "test-internal-secret-that-is-long-enough"
    settings.internal_auth_issuer = "main-backend"
    settings.internal_auth_audience = "microservice"
    settings.internal_auth_required_service = "futurex-reviewer-client"
    settings.api_rate_limit_enabled = False


def _token() -> str:
    return jwt.encode(
        {
            "sub": "main-backend",
            "service": "futurex-reviewer-client",
            "iss": settings.internal_auth_issuer,
            "aud": settings.internal_auth_audience,
        },
        settings.internal_auth_jwt_secret,
        algorithm=settings.internal_auth_algorithm,
    )


async def _insert_idea_lab_report() -> None:
    async with database.AsyncSessionLocal() as session:
        session.add(
            FeasibilityReport(
                conversation_id="conv-queue",
                idea_fit="Build a project reviewer",
                opportunity="Students need feedback after submitting repos",
                score="8",
                targeting="FutureX students",
                next_step="Review the repo",
            )
        )
        await session.commit()


def test_review_submit_enqueues_postgres_job_and_status_can_be_read(client):
    _configure_internal_auth()
    asyncio.run(_insert_idea_lab_report())

    enqueue = client.post(
        "/review",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "conversation_id": "conv-queue",
            "github_url": "https://github.com/example/project",
        },
    )

    assert enqueue.status_code == 202
    body = enqueue.json()
    assert body["status"] == "queued"
    assert body["conversation_id"] == "conv-queue"
    assert body["job_id"]

    by_job = client.get(body["status_url"], headers={"Authorization": f"Bearer {_token()}"})
    assert by_job.status_code == 200
    assert by_job.json()["status"] == "queued"

    by_conversation = client.get(
        "/review/conv-queue/job",
        headers={"Authorization": f"Bearer {_token()}"},
    )
    assert by_conversation.status_code == 200
    assert by_conversation.json()["job_id"] == body["job_id"]


def test_review_jobs_lists_previous_runs_with_state_and_output(client):
    _configure_internal_auth()
    asyncio.run(_insert_idea_lab_report())

    first = client.post(
        "/review",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "conversation_id": "conv-queue",
            "github_url": "https://github.com/example/first",
        },
    ).json()
    second = client.post(
        "/review",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "conversation_id": "conv-queue",
            "github_url": "https://github.com/example/second",
        },
    ).json()

    async def complete_first_job() -> None:
        async with database.AsyncSessionLocal() as session:
            await insert_review_job_event(
                session,
                job_id=first["job_id"],
                conversation_id="conv-queue",
                github_url="https://github.com/example/first",
                event_type="completed",
                payload={"report": {"summary": "Stored report output"}},
            )

    asyncio.run(complete_first_job())

    response = client.get("/review/jobs", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert {job["job_id"] for job in jobs} == {first["job_id"], second["job_id"]}
    completed = next(job for job in jobs if job["job_id"] == first["job_id"])
    queued = next(job for job in jobs if job["job_id"] == second["job_id"])
    assert completed["status"] == "completed"
    assert completed["report"] == {"summary": "Stored report output"}
    assert queued["status"] == "queued"


def test_progress_events_keep_job_status_started(client):
    _configure_internal_auth()

    async def insert_progress_events() -> dict:
        async with database.AsyncSessionLocal() as session:
            await insert_review_job_event(
                session,
                job_id="job-progress",
                conversation_id="conv-queue",
                github_url="https://github.com/example/project",
                event_type="queued",
            )
            await insert_review_job_event(
                session,
                job_id="job-progress",
                conversation_id="conv-queue",
                github_url="https://github.com/example/project",
                event_type="started",
            )
            await insert_review_job_event(
                session,
                job_id="job-progress",
                conversation_id="conv-queue",
                github_url="https://github.com/example/project",
                event_type="graph_extract_started",
                payload={"message": "Running Graphify extraction."},
            )
            await insert_review_job_event(
                session,
                job_id="job-progress",
                conversation_id="conv-queue",
                github_url="https://github.com/example/project",
                event_type="graph_summary_ready",
                payload={"summary_counts": {"files": 2}},
            )
            return await get_job_status(session, "job-progress")

    status = asyncio.run(insert_progress_events())

    assert status["status"] == "started"
    assert status["updated_at"] == status["events"][-1]["created_at"]
    assert [event["event_type"] for event in status["events"]] == [
        "queued",
        "started",
        "graph_extract_started",
        "graph_summary_ready",
    ]
