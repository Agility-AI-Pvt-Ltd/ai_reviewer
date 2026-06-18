import datetime as dt

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import get_ist_now


class GithubOAuthState(Base):
    __tablename__ = "github_oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    auth_identity: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    github_url: Mapped[str] = mapped_column(Text, nullable=False)
    repo_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=get_ist_now, nullable=False)


class GithubCredential(Base):
    __tablename__ = "github_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    auth_identity: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    github_login: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), default="bearer", nullable=False)
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=get_ist_now, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=get_ist_now, nullable=False)
