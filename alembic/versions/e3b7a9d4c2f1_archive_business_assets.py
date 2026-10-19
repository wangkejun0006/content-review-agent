"""Add reversible archive state to operator-facing assets.

Revision ID: e3b7a9d4c2f1
Revises: d8a4f6c1e2b7
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e3b7a9d4c2f1"
down_revision: str | None = "d8a4f6c1e2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "registry_items",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_briefs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "growth_runs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("growth_runs", "archived_at")
    op.drop_column("campaign_briefs", "archived_at")
    op.drop_column("registry_items", "archived_at")
