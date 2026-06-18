"""Add GitHub OAuth tables

Revision ID: 6d8ef3b69d21
Revises: d659050b5ca8
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d8ef3b69d21"
down_revision: Union[str, Sequence[str], None] = "d659050b5ca8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "github_oauth_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("auth_identity", sa.String(length=255), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("github_url", sa.Text(), nullable=False),
        sa.Column("repo_owner", sa.String(length=255), nullable=False),
        sa.Column("repo_name", sa.String(length=255), nullable=False),
        sa.Column("requested_scope", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state"),
    )
    op.create_index(op.f("ix_github_oauth_states_id"), "github_oauth_states", ["id"], unique=False)
    op.create_index(
        op.f("ix_github_oauth_states_state"),
        "github_oauth_states",
        ["state"],
        unique=True,
    )
    op.create_index(
        op.f("ix_github_oauth_states_auth_identity"),
        "github_oauth_states",
        ["auth_identity"],
        unique=False,
    )

    op.create_table(
        "github_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auth_identity", sa.String(length=255), nullable=False),
        sa.Column("github_login", sa.String(length=255), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_github_credentials_id"), "github_credentials", ["id"], unique=False)
    op.create_index(
        op.f("ix_github_credentials_auth_identity"),
        "github_credentials",
        ["auth_identity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_credentials_github_login"),
        "github_credentials",
        ["github_login"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_github_credentials_github_login"), table_name="github_credentials")
    op.drop_index(op.f("ix_github_credentials_auth_identity"), table_name="github_credentials")
    op.drop_index(op.f("ix_github_credentials_id"), table_name="github_credentials")
    op.drop_table("github_credentials")
    op.drop_index(op.f("ix_github_oauth_states_auth_identity"), table_name="github_oauth_states")
    op.drop_index(op.f("ix_github_oauth_states_state"), table_name="github_oauth_states")
    op.drop_index(op.f("ix_github_oauth_states_id"), table_name="github_oauth_states")
    op.drop_table("github_oauth_states")
