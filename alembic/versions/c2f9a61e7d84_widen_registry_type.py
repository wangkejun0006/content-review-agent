"""Widen registry type for marketing program assets.

Revision ID: c2f9a61e7d84
Revises: b4e81f0c2a63
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2f9a61e7d84"
down_revision: str | None = "b4e81f0c2a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "registry_items",
        "registry_type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=40),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "registry_items",
        "registry_type",
        existing_type=sa.String(length=40),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
