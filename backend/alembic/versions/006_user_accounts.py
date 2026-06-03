"""Add user_accounts table for multi-user key wrapping.

Revision ID: 006_user_accounts
Revises: 005_auto_unlock_token
Create Date: 2026-04-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_user_accounts"
down_revision: str | Sequence[str] | None = "005_auto_unlock_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("sentinel_ciphertext", sa.Text(), nullable=False),
        sa.Column("wrapped_fernet_keys", sa.Text(), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_accounts")
