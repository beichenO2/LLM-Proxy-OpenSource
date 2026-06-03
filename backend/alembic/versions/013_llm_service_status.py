"""Add LLMServiceStatus table for tracking last call status (R11).

Revision ID: 013_llm_service_status
Revises: 012_binding_fallback
Create Date: 2026-05-11

Records the result of the most recent call to each LLM service,
enabling status dashboards without additional API calls.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "013_llm_service_status"
down_revision: str = "012_binding_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_service_status",
        sa.Column("service_name", sa.String(255), primary_key=True),
        sa.Column("last_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_call_status", sa.String(32), nullable=True),
        sa.Column("last_call_error", sa.Text(), nullable=True),
        sa.Column("last_call_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("llm_service_status")