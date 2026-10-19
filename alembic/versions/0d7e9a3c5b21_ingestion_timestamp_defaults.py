"""Add ingestion record timestamp defaults.

Revision ID: 0d7e9a3c5b21
Revises: f4c8b2e6a1d3
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0d7e9a3c5b21"
down_revision: str | None = "f4c8b2e6a1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "ingestion_records",
        "created_at",
        server_default=sa.func.now(),
    )
    op.alter_column(
        "ingestion_records",
        "updated_at",
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    op.alter_column("ingestion_records", "updated_at", server_default=None)
    op.alter_column("ingestion_records", "created_at", server_default=None)
