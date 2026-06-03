"""Drop service_tokens table — plaintext export ban.

Service tokens allowed bearer-authenticated callers to reach reveal endpoints.
All service-to-service auth now goes through proxy/sign/d-class interfaces.

Revision ID: 011
"""

from alembic import op
import sqlalchemy as sa

revision: str = "011_drop_service_tokens"
down_revision: str = "010_service_tokens"


def upgrade() -> None:
    op.drop_table("service_tokens")


def downgrade() -> None:
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
