"""app_settings table for API port and JSON preferences (STNG-01, STNG-03)

Revision ID: 004_app_settings
Revises: 003_proxy_binding_auth_header
Create Date: 2026-04-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_app_settings"
down_revision: str | Sequence[str] | None = "003_proxy_binding_auth_header"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_port", sa.Integer(), nullable=True),
        sa.Column("preferences_json", sa.Text(), nullable=True, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO app_settings (id, api_port, preferences_json) VALUES (1, NULL, '{}')"
        )
    )


def downgrade() -> None:
    op.drop_table("app_settings")
