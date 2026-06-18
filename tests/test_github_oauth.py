import asyncio
import datetime as dt
from urllib.parse import parse_qs, urlparse

import jwt
from sqlalchemy import select

from app.core import database
from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.core.time import get_ist_now
from app.models.github_auth import GithubCredential, GithubOAuthState
from app.models.idea_lab import FeasibilityReport
from app.models.review_job import ReviewJobEvent


def _configure_internal_auth() -> None:
    settings.internal_auth_enabled = True
    settings.internal_auth_algorithm = "HS256"
    settings.internal_auth_jwt_secret = "test-internal-secret-that-is-long-enough"
    settings.internal_auth_issuer = "main-backend"
    settings.internal_auth_audience = "microservice"
    settings.internal_auth_required_service = "futurex-reviewer-client"
    settings.api_rate_limit_enabled = False


def _configure_github_oauth() -> None:
    settings.github_oauth_enabled = True
    settings.github_client_id = "github-client-id"
    settings.github_client_secret = "github-client-secret"
    settings.github_oauth_callback_url = "https://api.futurex.ai/auth/github/callback"
    settings.github_oauth_scope = "repo"
    settings.github_token_encryption_key = "test-token-encryption-key"


def _token() -> str:
    return jwt.encode(
        {
            "sub": "user-123",
            "service": "futurex-reviewer-client",
            "iss": settings.internal_auth_issuer,
            "aud": settings.internal_auth_audience,
        },
        settings.internal_auth_jwt_secret,
        algorithm=settings.internal_auth_algorithm,
    )


async def _insert_idea_lab_report(conversation_id: str = "conv-private") -> None:
    async with database.AsyncSessionLocal() as session:
        session.add(
            FeasibilityReport(
                conversation_id=conversation_id,
                idea_fit="Build a private repo reviewer",
                opportunity="Students need private repo feedback",
                score="8",
                targeting="FutureX students",
                next_step="Review the repo",
            )
        )
        await session.commit()


def test_private_repo_start_returns_github_oauth_url(monkeypatch, client):
    _configure_internal_auth()
    _configure_github_oauth()
    asyncio.run(_insert_idea_lab_report())

    async def fake_accessible(github_url, access_token=None):
        assert github_url == "https://github.com/example/private"
        assert access_token is None
        return False

    monkeypatch.setattr("app.api.routes.review.github_repository_accessible", fake_accessible)

    response = client.post(
        "/review/start",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "conversation_id": "conv-private",
            "github_url": "https://github.com/example/private",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requires_auth"] is True
    assert body["status"] == "requires_auth"
    parsed = urlparse(body["oauth_url"])
    assert parsed.netloc == "github.com"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["github-client-id"]
    assert query["scope"] == ["repo"]
    assert query["redirect_uri"] == ["https://api.futurex.ai/auth/github/callback"]

    async def load_state():
        async with database.AsyncSessionLocal() as session:
            result = await session.execute(select(GithubOAuthState))
            return result.scalar_one()

    oauth_state = asyncio.run(load_state())
    assert body["state"] == oauth_state.state
    assert oauth_state.auth_identity == "user-123"
    assert oauth_state.repo_owner == "example"
    assert oauth_state.repo_name == "private"


def test_github_callback_stores_encrypted_token_and_queues_job(monkeypatch, client):
    _configure_internal_auth()
    _configure_github_oauth()
    asyncio.run(_insert_idea_lab_report())

    async def seed_state() -> str:
        async with database.AsyncSessionLocal() as session:
            oauth_state = GithubOAuthState(
                state="oauth-state",
                auth_identity="user-123",
                conversation_id="conv-private",
                github_url="https://github.com/example/private",
                repo_owner="example",
                repo_name="private",
                requested_scope="repo",
                expires_at=get_ist_now() + dt.timedelta(hours=1),
            )
            session.add(oauth_state)
            await session.commit()
            return oauth_state.state

    state = asyncio.run(seed_state())

    async def fake_exchange(code):
        assert code == "code-123"
        return {"access_token": "gho_private_token", "token_type": "bearer", "scope": "repo"}

    async def fake_user(access_token):
        assert access_token == "gho_private_token"
        return {"login": "octo-user"}

    async def fake_accessible(github_url, access_token=None):
        assert github_url == "https://github.com/example/private"
        assert access_token == "gho_private_token"
        return True

    monkeypatch.setattr("app.api.routes.auth.exchange_github_code", fake_exchange)
    monkeypatch.setattr("app.api.routes.auth.fetch_github_user", fake_user)
    monkeypatch.setattr("app.api.routes.auth.github_repository_accessible", fake_accessible)

    response = client.get(f"/auth/github/callback?code=code-123&state={state}")

    assert response.status_code == 202
    body = response.json()
    assert body["requires_auth"] is False
    assert body["status"] == "queued"
    assert body["conversation_id"] == "conv-private"

    async def load_records():
        async with database.AsyncSessionLocal() as session:
            credential = (await session.execute(select(GithubCredential))).scalar_one()
            queued = await session.execute(select(ReviewJobEvent))
            return credential, queued.scalar_one()

    credential, queued_event = asyncio.run(load_records())
    assert credential.github_login == "octo-user"
    assert "gho_private_token" not in credential.encrypted_access_token
    assert decrypt_secret(credential.encrypted_access_token) == "gho_private_token"
    assert queued_event.payload["github_credential_id"] == credential.id
