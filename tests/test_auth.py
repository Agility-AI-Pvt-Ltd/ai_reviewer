import jwt

from app.core.config import settings


def _configure_internal_auth() -> None:
    settings.internal_auth_enabled = True
    settings.internal_auth_algorithm = "HS256"
    settings.internal_auth_jwt_secret = "test-internal-secret"
    settings.internal_auth_issuer = "main-backend"
    settings.internal_auth_audience = "microservice"
    settings.internal_auth_required_service = "futurex-reviewer-client"
    settings.api_rate_limit_enabled = False


def _token(service: str = "futurex-reviewer-client") -> str:
    return jwt.encode(
        {
            "sub": "main-backend",
            "service": service,
            "iss": settings.internal_auth_issuer,
            "aud": settings.internal_auth_audience,
        },
        settings.internal_auth_jwt_secret,
        algorithm=settings.internal_auth_algorithm,
    )


def test_internal_auth_verify_requires_bearer_token(client):
    _configure_internal_auth()

    no_token = client.get("/auth/verify")
    assert no_token.status_code == 401

    malformed = client.get("/auth/verify", headers={"Authorization": "Token nope"})
    assert malformed.status_code == 401


def test_internal_auth_verify_accepts_valid_service_token(client):
    _configure_internal_auth()

    response = client.get("/auth/verify", headers={"Authorization": f"Bearer {_token()}"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["auth"]["service"] == "futurex-reviewer-client"


def test_internal_auth_verify_rejects_wrong_service_claim(client):
    _configure_internal_auth()

    response = client.get("/auth/verify", headers={"Authorization": f"Bearer {_token('other-service')}"})
    assert response.status_code == 401


def test_review_requires_bearer_token(client):
    _configure_internal_auth()

    response = client.post(
        "/review",
        json={"github_url": "https://github.com/openai/openai-python", "conversation_id": "abc"},
    )
    assert response.status_code == 401
