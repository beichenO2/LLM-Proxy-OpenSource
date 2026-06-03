"""Add fallback chain fields to Binding table (R10).

Revision ID: 012_binding_fallback
Revises: 011_drop_service_tokens
Create Date: 2026-05-10

Supports multi-key rotation and cross-provider failover for LLM Proxy.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012_binding_fallback"
down_revision: str = "011_drop_service_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add fallback_chain: JSON array of service_name strings
    op.add_column(
        "bindings",
        sa.Column("fallback_chain", sa.Text(), nullable=True),
    )
    # Add priority: weight for load balancing
    op.add_column(
        "bindings",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
    )
    # Add cooldown_until: timestamp when binding can be used again
    op.add_column(
        "bindings",
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
    )
    # Add consecutive_failures: reset on success
    op.add_column(
        "bindings",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("bindings", "consecutive_failures")
    op.drop_column("bindings", "cooldown_until")
    op.drop_column("bindings", "priority")
    op.drop_column("bindings", "fallback_chain")
