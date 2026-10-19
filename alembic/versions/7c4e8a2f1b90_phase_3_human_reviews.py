"""Phase 3 human review idempotency.

Revision ID: 7c4e8a2f1b90
Revises: 2f6a1d904c7b
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c4e8a2f1b90"
down_revision: str | None = "2f6a1d904c7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("human_reviews", sa.Column("content_version_id", sa.Uuid(), nullable=True))
    op.add_column("human_reviews", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.execute("UPDATE human_reviews SET idempotency_key = id::text")
    op.alter_column("human_reviews", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_human_reviews_brand_id_idempotency_key",
        "human_reviews",
        ["brand_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_human_reviews_brand_id_idempotency_key",
        "human_reviews",
        type_="unique",
    )
    op.drop_column("human_reviews", "idempotency_key")
    op.drop_column("human_reviews", "content_version_id")
