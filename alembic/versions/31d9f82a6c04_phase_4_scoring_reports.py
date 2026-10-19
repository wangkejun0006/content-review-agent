"""Phase 4 governed scoring reports.

Revision ID: 31d9f82a6c04
Revises: 7c4e8a2f1b90
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "31d9f82a6c04"
down_revision: str | None = "7c4e8a2f1b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("growth_runs", sa.Column("recommended_candidate_id", sa.Uuid(), nullable=True))
    op.add_column("growth_runs", sa.Column("selected_candidate_id", sa.Uuid(), nullable=True))
    op.add_column("score_reports", sa.Column("prompt_revision_id", sa.Uuid(), nullable=True))
    op.add_column(
        "score_reports",
        sa.Column("pass_threshold", sa.Integer(), nullable=False, server_default="70"),
    )
    op.add_column(
        "score_reports", sa.Column("summary", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "score_reports",
        sa.Column(
            "revision_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column("score_reports", sa.Column("input_checksum", sa.String(64), nullable=True))
    op.add_column("score_reports", sa.Column("generation_key", sa.String(64), nullable=True))
    op.execute(
        "UPDATE score_reports SET "
        "prompt_revision_id = '00000000-0000-0000-0000-000000000000', "
        "input_checksum = repeat('0', 64), "
        "generation_key = md5(id::text) || md5(id::text)"
    )
    op.alter_column("score_reports", "prompt_revision_id", nullable=False)
    op.alter_column("score_reports", "input_checksum", nullable=False)
    op.alter_column("score_reports", "generation_key", nullable=False)
    op.create_unique_constraint(
        "uq_score_reports_content_version_id", "score_reports", ["content_version_id"]
    )
    op.create_unique_constraint(
        "uq_score_reports_generation_key", "score_reports", ["generation_key"]
    )
    op.create_foreign_key(
        "fk_score_reports_content_version_id_content_versions",
        "score_reports",
        "content_versions",
        ["content_version_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_score_reports_content_version_id_content_versions",
        "score_reports",
        type_="foreignkey",
    )
    op.drop_constraint("uq_score_reports_generation_key", "score_reports", type_="unique")
    op.drop_constraint(
        "uq_score_reports_content_version_id", "score_reports", type_="unique"
    )
    op.drop_column("score_reports", "generation_key")
    op.drop_column("score_reports", "input_checksum")
    op.drop_column("score_reports", "revision_suggestions")
    op.drop_column("score_reports", "summary")
    op.drop_column("score_reports", "pass_threshold")
    op.drop_column("score_reports", "prompt_revision_id")
    op.drop_column("growth_runs", "selected_candidate_id")
    op.drop_column("growth_runs", "recommended_candidate_id")
