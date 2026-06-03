"""Add binding_secrets table and bindings.key column for sign providers.

Revision ID: 014_binding_secrets
Revises: 013_llm_service_status
Create Date: 2026-05-11

Sign providers (weex, feishu-webhook, aliyun-sigv1) require multiple secrets
per binding. This migration adds:
- binding_secrets table: many-to-many association between Binding and Secret
- bindings.key column: unique identifier for sign provider bindings

Note: SQLite doesn't support ALTER COLUMN, so we use batch operations.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "014_binding_secrets"
down_revision: str = "013_llm_service_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add key column to bindings table (nullable, for sign provider bindings)
    op.add_column(
        "bindings",
        sa.Column("key", sa.String(512), nullable=True),
    )
    op.create_index("ix_bindings_key", "bindings", ["key"])

    # Create binding_secrets association table
    op.create_table(
        "binding_secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("binding_id", sa.String(36), sa.ForeignKey("bindings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("secret_id", sa.String(36), sa.ForeignKey("secrets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_binding_secrets_binding_id", "binding_secrets", ["binding_id"])
    op.create_index("ix_binding_secrets_secret_id", "binding_secrets", ["secret_id"])

    # Use batch operations for SQLite compatibility to make secret_ref_key nullable
    with op.batch_alter_table("bindings", schema=None) as batch_op:
        batch_op.alter_column("secret_ref_key", nullable=True)


def downgrade() -> None:
    op.drop_index("ix_binding_secrets_secret_id", "binding_secrets")
    op.drop_index("ix_binding_secrets_binding_id", "binding_secrets")
    op.drop_table("binding_secrets")

    # Revert secret_ref_key to not nullable (batch for SQLite)
    with op.batch_alter_table("bindings", schema=None) as batch_op:
        batch_op.alter_column("secret_ref_key", nullable=False)

    op.drop_index("ix_bindings_key", "bindings")
    op.drop_column("bindings", "key")
