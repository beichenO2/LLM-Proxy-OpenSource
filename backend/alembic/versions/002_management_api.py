"""management api schema

Revision ID: 002_management_api
Revises: 001_initial
Create Date: 2026-04-06

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "002_management_api"
down_revision: str | Sequence[str] | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("identities") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )

    op.add_column("secrets", sa.Column("base_url", sa.Text(), nullable=True))
    op.add_column("secrets", sa.Column("category", sa.String(length=128), nullable=True))
    op.add_column(
        "secrets",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("secrets") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )

    with op.batch_alter_table("bindings") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )

    op.create_index(
        "uq_identities_key_global",
        "identities",
        ["key"],
        unique=True,
        sqlite_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_secrets_key_global",
        "secrets",
        ["key"],
        unique=True,
        sqlite_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_bindings_service_global",
        "bindings",
        ["service_name"],
        unique=True,
        sqlite_where=sa.text("project_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bindings_service_global", table_name="bindings")
    op.drop_index("uq_secrets_key_global", table_name="secrets")
    op.drop_index("uq_identities_key_global", table_name="identities")

    with op.batch_alter_table("bindings") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    with op.batch_alter_table("secrets") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    op.drop_column("secrets", "rotated_at")
    op.drop_column("secrets", "category")
    op.drop_column("secrets", "base_url")

    with op.batch_alter_table("identities") as batch_op:
        batch_op.alter_column(
            "project_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
