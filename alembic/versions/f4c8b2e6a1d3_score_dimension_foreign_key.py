"""Add score dimension ownership foreign key.

Revision ID: f4c8b2e6a1d3
Revises: e3b7a9d4c2f1
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4c8b2e6a1d3"
down_revision: str | None = "e3b7a9d4c2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM score_dimensions
        WHERE report_id NOT IN (SELECT id FROM score_reports)
        """
    )
    op.create_foreign_key(
        "fk_score_dimensions_report_id_score_reports",
        "score_dimensions",
        "score_reports",
        ["report_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_score_dimensions_report_id_score_reports",
        "score_dimensions",
        type_="foreignkey",
    )
