"""Add identity_bindings table for cross-service user federation.

Revision ID: 009_identity_bindings
Revises: 008_browser_sessions
Create Date: 2026-04-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_identity_bindings"
down_revision: str | Sequence[str] | None = "008_browser_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("external_username", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("service", "external_username", name="uq_service_external_user"),
    )


def downgrade() -> None:
    op.drop_table("identity_bindings")
