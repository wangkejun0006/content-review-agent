"""Add product media timestamp defaults.

Revision ID: 9a4f3c2d7e11
Revises: 8e2c7a1b5d90
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a4f3c2d7e11"
down_revision: str | None = "8e2c7a1b5d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "product_media_assets",
        "created_at",
        server_default=sa.func.now(),
    )
    op.alter_column(
        "product_media_assets",
        "updated_at",
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    op.alter_column("product_media_assets", "updated_at", server_default=None)
    op.alter_column("product_media_assets", "created_at", server_default=None)
