"""Phase 5 analytics governance.

Revision ID: 4a8c2d61e903
Revises: 31d9f82a6c04
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4a8c2d61e903"
down_revision: str | None = "31d9f82a6c04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("metric_snapshots", sa.Column("corrects_snapshot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_metric_snapshots_corrects_snapshot_id",
        "metric_snapshots",
        "metric_snapshots",
        ["corrects_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_publications_content_version_id",
        "publications",
        "content_versions",
        ["content_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_metric_snapshots_publication_id",
        "metric_snapshots",
        "publications",
        ["publication_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_commerce_scope_capture",
        "commerce_snapshots",
        ["brand_id", "scope_type", "scope_key", "captured_at"],
    )
    op.create_foreign_key(
        "fk_attribution_evidence_publication_id",
        "attribution_evidence",
        "publications",
        ["publication_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_attribution_evidence_commerce_snapshot_id",
        "attribution_evidence",
        "commerce_snapshots",
        ["commerce_snapshot_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_attribution_evidence_link",
        "attribution_evidence",
        ["publication_id", "commerce_snapshot_id", "evidence_type"],
    )
    op.add_column("feedback_runs", sa.Column("thread_id", sa.String(100), nullable=True))
    op.execute("UPDATE feedback_runs SET thread_id = id::text WHERE thread_id IS NULL")
    op.alter_column("feedback_runs", "thread_id", nullable=False)
    op.create_unique_constraint("uq_feedback_runs_thread_id", "feedback_runs", ["thread_id"])
    op.add_column(
        "feedback_runs",
        sa.Column(
            "commerce_snapshot_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "feedback_runs",
        sa.Column(
            "attribution_evidence_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("feedback_runs", sa.Column("prompt_revision_id", sa.Uuid(), nullable=True))
    op.add_column("feedback_runs", sa.Column("input_checksum", sa.String(64), nullable=True))
    op.add_column("feedback_runs", sa.Column("error", postgresql.JSONB(), nullable=True))
    op.add_column(
        "feedback_recommendations",
        sa.Column("attribution_scope", sa.String(20), nullable=True),
    )
    op.add_column(
        "feedback_recommendations", sa.Column("input_checksum", sa.String(64), nullable=True)
    )
    op.add_column(
        "feedback_recommendations", sa.Column("generation_key", sa.String(64), nullable=True)
    )
    op.create_foreign_key(
        "fk_feedback_recommendations_feedback_run_id",
        "feedback_recommendations",
        "feedback_runs",
        ["feedback_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_feedback_recommendations_strategy_insight_revision_id",
        "feedback_recommendations",
        "registry_revisions",
        ["strategy_insight_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_feedback_recommendations_feedback_run_id",
        "feedback_recommendations",
        ["feedback_run_id"],
    )
    op.create_unique_constraint(
        "uq_feedback_recommendations_generation_key",
        "feedback_recommendations",
        ["generation_key"],
    )
    op.create_table(
        "feedback_run_registry_snapshots",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_run_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feedback_run_id"], ["feedback_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feedback_run_id", "revision_id"),
    )
    op.create_index(
        "ix_feedback_run_registry_snapshots_brand_id",
        "feedback_run_registry_snapshots",
        ["brand_id"],
    )
    op.create_index(
        "ix_feedback_run_registry_snapshots_feedback_run_id",
        "feedback_run_registry_snapshots",
        ["feedback_run_id"],
    )
    op.create_table(
        "import_batches",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("import_type", sa.String(50), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "idempotency_key"),
    )
    op.create_index("ix_import_batches_brand_id", "import_batches", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_import_batches_brand_id", table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_index(
        "ix_feedback_run_registry_snapshots_feedback_run_id",
        table_name="feedback_run_registry_snapshots",
    )
    op.drop_index(
        "ix_feedback_run_registry_snapshots_brand_id",
        table_name="feedback_run_registry_snapshots",
    )
    op.drop_table("feedback_run_registry_snapshots")
    op.drop_constraint(
        "uq_feedback_recommendations_generation_key",
        "feedback_recommendations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_feedback_recommendations_feedback_run_id",
        "feedback_recommendations",
        type_="unique",
    )
    op.drop_constraint(
        "fk_feedback_recommendations_strategy_insight_revision_id",
        "feedback_recommendations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_feedback_recommendations_feedback_run_id",
        "feedback_recommendations",
        type_="foreignkey",
    )
    op.drop_column("feedback_recommendations", "generation_key")
    op.drop_column("feedback_recommendations", "input_checksum")
    op.drop_column("feedback_recommendations", "attribution_scope")
    op.drop_column("feedback_runs", "error")
    op.drop_column("feedback_runs", "input_checksum")
    op.drop_column("feedback_runs", "prompt_revision_id")
    op.drop_column("feedback_runs", "attribution_evidence_ids")
    op.drop_column("feedback_runs", "commerce_snapshot_ids")
    op.drop_constraint("uq_feedback_runs_thread_id", "feedback_runs", type_="unique")
    op.drop_column("feedback_runs", "thread_id")
    op.drop_constraint("uq_attribution_evidence_link", "attribution_evidence", type_="unique")
    op.drop_constraint(
        "fk_attribution_evidence_commerce_snapshot_id",
        "attribution_evidence",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_attribution_evidence_publication_id",
        "attribution_evidence",
        type_="foreignkey",
    )
    op.drop_constraint("uq_commerce_scope_capture", "commerce_snapshots", type_="unique")
    op.drop_constraint(
        "fk_metric_snapshots_publication_id", "metric_snapshots", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_publications_content_version_id", "publications", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_metric_snapshots_corrects_snapshot_id", "metric_snapshots", type_="foreignkey"
    )
    op.drop_column("metric_snapshots", "corrects_snapshot_id")
