import datetime as dt
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.time import get_ist_now
from app.models.github_auth import GithubCredential, GithubOAuthState
from app.utils.file_handler import parse_github_repo_url

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


def github_auth_identity(auth_payload: dict[str, Any] | None) -> str:
    auth_payload = auth_payload or {}
    for key in ("user_id", "uid", "sub", "service"):
        value = auth_payload.get(key)
        if value:
            return str(value)
    return "anonymous"


def github_oauth_configured() -> bool:
    return bool(
        settings.github_client_id
        and settings.github_client_secret
        and settings.github_oauth_callback_url
    )


def build_github_oauth_url(state: str) -> str:
    if not settings.github_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth client id is not configured.",
        )
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_oauth_callback_url or "",
            "scope": settings.github_oauth_scope,
            "state": state,
        }
    )
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


async def create_github_oauth_state(
    session: AsyncSession,
    *,
    auth_identity: str,
    conversation_id: str,
    github_url: str,
) -> GithubOAuthState:
    owner, repo = parse_github_repo_url(github_url)
    now = get_ist_now()
    oauth_state = GithubOAuthState(
        state=secrets.token_urlsafe(32),
        auth_identity=auth_identity,
        conversation_id=conversation_id,
        github_url=github_url,
        repo_owner=owner,
        repo_name=repo,
        requested_scope=settings.github_oauth_scope,
        expires_at=now + dt.timedelta(seconds=settings.github_oauth_state_ttl_seconds),
    )
    session.add(oauth_state)
    await session.commit()
    await session.refresh(oauth_state)
    return oauth_state


async def consume_github_oauth_state(session: AsyncSession, state: str) -> GithubOAuthState:
    result = await session.execute(select(GithubOAuthState).where(GithubOAuthState.state == state))
    oauth_state = result.scalar_one_or_none()
    if oauth_state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid GitHub OAuth state.")
    if oauth_state.consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub OAuth state was already used.")
    if oauth_state.expires_at < get_ist_now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub OAuth state expired.")

    oauth_state.consumed_at = get_ist_now()
    await session.commit()
    await session.refresh(oauth_state)
    return oauth_state


async def exchange_github_code(code: str) -> dict[str, Any]:
    if not github_oauth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not fully configured.",
        )

    async with httpx.AsyncClient(timeout=settings.github_api_timeout_seconds) as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_callback_url,
            },
            headers={"Accept": "application/json"},
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=payload.get("error_description") or payload["error"],
        )
    if not payload.get("access_token"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub did not return an access token.",
        )
    return payload


async def fetch_github_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.github_api_timeout_seconds) as client:
        response = await client.get(
            f"{GITHUB_API_URL}/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    response.raise_for_status()
    return response.json()


async def github_repository_accessible(github_url: str, access_token: str | None = None) -> bool:
    owner, repo = parse_github_repo_url(github_url)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient(timeout=settings.github_api_timeout_seconds) as client:
        response = await client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}", headers=headers)

    if response.status_code == status.HTTP_200_OK:
        return True
    if response.status_code in {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND}:
        return False
    response.raise_for_status()
    return False


async def find_latest_github_credential(
    session: AsyncSession,
    *,
    auth_identity: str,
) -> GithubCredential | None:
    result = await session.execute(
        select(GithubCredential)
        .where(GithubCredential.auth_identity == auth_identity)
        .order_by(GithubCredential.updated_at.desc(), GithubCredential.id.desc())
        .limit(1)
    )
    credential = result.scalar_one_or_none()
    if credential and credential.expires_at and credential.expires_at < get_ist_now():
        return None
    return credential


async def get_github_access_token(session: AsyncSession, credential_id: int) -> str:
    credential = await session.get(GithubCredential, credential_id)
    if credential is None:
        raise ValueError("GitHub credential was not found.")
    if credential.expires_at and credential.expires_at < get_ist_now():
        raise ValueError("GitHub credential is expired.")
    return decrypt_secret(credential.encrypted_access_token)


async def store_github_credential(
    session: AsyncSession,
    *,
    auth_identity: str,
    token_payload: dict[str, Any],
    github_user: dict[str, Any] | None = None,
) -> GithubCredential:
    access_token = str(token_payload["access_token"])
    expires_at = None
    if token_payload.get("expires_in"):
        expires_at = get_ist_now() + dt.timedelta(seconds=int(token_payload["expires_in"]))

    credential = GithubCredential(
        auth_identity=auth_identity,
        github_login=(github_user or {}).get("login"),
        encrypted_access_token=encrypt_secret(access_token),
        token_type=token_payload.get("token_type") or "bearer",
        scope=token_payload.get("scope"),
        expires_at=expires_at,
        updated_at=get_ist_now(),
    )
    session.add(credential)
    await session.commit()
    await session.refresh(credential)
    return credential
