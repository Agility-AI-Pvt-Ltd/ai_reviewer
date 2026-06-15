import asyncio

import jwt

from app.core import database
from app.core.config import settings
from app.schemas.idea_lab import IdeaLabReport
from app.services.review_state import insert_review_state_snapshot


def _configure_internal_auth() -> None:
    settings.internal_auth_enabled = True
    settings.internal_auth_algorithm = "HS256"
    settings.internal_auth_jwt_secret = "test-internal-secret"
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


async def _insert_snapshot() -> None:
    async with database.AsyncSessionLocal() as session:
        await insert_review_state_snapshot(
            session,
            conversation_id="conv-1",
            github_url="https://github.com/example/project",
            stage="graph_extracted",
            state={"conversation_id": "conv-1", "github_url": "https://github.com/example/project"},
            idea_lab_report=IdeaLabReport(conversation_id="conv-1", idea_fit="Build a review tool"),
            graphify_graph_json={"nodes": [], "edges": [], "communities": []},
            graph={"nodes": [], "edges": []},
            graph_summary={"files": ["app/main.py"], "functions": [], "classes": []},
        )


def test_review_state_snapshots_are_read_from_postgres(client):
    _configure_internal_auth()
    asyncio.run(_insert_snapshot())

    response = client.get(
        "/review/conv-1/state",
        headers={"Authorization": f"Bearer {_token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["conversation_id"] == "conv-1"
    assert body[0]["stage"] == "graph_extracted"
    assert body[0]["graphify_graph_json"]["communities"] == []
    assert body[0]["graph_summary"]["files"] == ["app/main.py"]
