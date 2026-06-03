"""Add auto_unlock_token to db_metadata for device-local vault auto-unlock.

Revision ID: 005_auto_unlock_token
Revises: 004_app_settings
Create Date: 2026-04-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_auto_unlock_token"
down_revision: str | Sequence[str] | None = "004_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("db_metadata", sa.Column("auto_unlock_token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("db_metadata", "auto_unlock_token")
