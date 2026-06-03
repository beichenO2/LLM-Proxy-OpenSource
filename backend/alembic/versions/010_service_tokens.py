"""Add service_tokens table for bearer token auth.

Revision ID: 010
"""

from alembic import op
import sqlalchemy as sa

revision: str = "010_service_tokens"
down_revision: str = "009_identity_bindings"


def upgrade() -> None:
    op.create_table(
        "service_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_name", sa.String(128), nullable=False, index=True),
        sa.Column("token_hash", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("token_prefix", sa.String(12), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="service"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("service_tokens")
