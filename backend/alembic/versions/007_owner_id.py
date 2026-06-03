"""Add owner_id to identities and secrets for per-user data isolation.

Revision ID: 007_owner_id
Revises: 006_user_accounts
Create Date: 2026-04-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_owner_id"
down_revision: str | Sequence[str] | None = "006_user_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("identities") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_identities_owner_id", ["owner_id"])
        batch_op.create_foreign_key(
            "fk_identities_owner_id",
            "user_accounts",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("secrets") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_secrets_owner_id", ["owner_id"])
        batch_op.create_foreign_key(
            "fk_secrets_owner_id",
            "user_accounts",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("secrets") as batch_op:
        batch_op.drop_constraint("fk_secrets_owner_id", type_="foreignkey")
        batch_op.drop_index("ix_secrets_owner_id")
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("identities") as batch_op:
        batch_op.drop_constraint("fk_identities_owner_id", type_="foreignkey")
        batch_op.drop_index("ix_identities_owner_id")
        batch_op.drop_column("owner_id")
