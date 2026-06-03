"""proxy binding auth_header column (D-64)

Revision ID: 003_proxy_binding_auth_header
Revises: 002_management_api
Create Date: 2026-04-07

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "003_proxy_binding_auth_header"
down_revision: str | Sequence[str] | None = "002_management_api"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bindings",
        sa.Column("auth_header", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bindings", "auth_header")
