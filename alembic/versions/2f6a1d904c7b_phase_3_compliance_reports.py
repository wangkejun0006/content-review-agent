"""Phase 3 governed compliance reports.

Revision ID: 2f6a1d904c7b
Revises: 9b21d8f6a4c2
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2f6a1d904c7b"
down_revision: str | None = "9b21d8f6a4c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("compliance_reports", sa.Column("prompt_revision_id", sa.Uuid(), nullable=True))
    op.add_column(
        "compliance_reports",
        sa.Column("deterministic_pass", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "compliance_reports",
        sa.Column("semantic_pass", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("compliance_reports", sa.Column("input_checksum", sa.String(64), nullable=True))
    op.add_column("compliance_reports", sa.Column("generation_key", sa.String(64), nullable=True))
    op.execute(
        "UPDATE compliance_reports SET "
        "prompt_revision_id = '00000000-0000-0000-0000-000000000000', "
        "input_checksum = repeat('0', 64), "
        "generation_key = md5(id::text) || md5(id::text)"
    )
    op.alter_column("compliance_reports", "prompt_revision_id", nullable=False)
    op.alter_column("compliance_reports", "input_checksum", nullable=False)
    op.alter_column("compliance_reports", "generation_key", nullable=False)
    op.create_unique_constraint(
        "uq_compliance_reports_content_version_id",
        "compliance_reports",
        ["content_version_id"],
    )
    op.create_unique_constraint(
        "uq_compliance_reports_generation_key", "compliance_reports", ["generation_key"]
    )
    op.create_foreign_key(
        "fk_compliance_reports_content_version_id_content_versions",
        "compliance_reports",
        "content_versions",
        ["content_version_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "compliance_findings",
        sa.Column("source", sa.String(30), nullable=False, server_default="deterministic"),
    )
    op.add_column(
        "compliance_findings",
        sa.Column("evidence_excerpt", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "compliance_findings",
        sa.Column("suggestion", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("compliance_findings", sa.Column("rule_revision_id", sa.Uuid(), nullable=True))
    op.add_column("compliance_findings", sa.Column("claim_revision_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_compliance_findings_report_id_compliance_reports",
        "compliance_findings",
        "compliance_reports",
        ["report_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_compliance_findings_report_id_compliance_reports",
        "compliance_findings",
        type_="foreignkey",
    )
    op.drop_column("compliance_findings", "claim_revision_id")
    op.drop_column("compliance_findings", "rule_revision_id")
    op.drop_column("compliance_findings", "suggestion")
    op.drop_column("compliance_findings", "evidence_excerpt")
    op.drop_column("compliance_findings", "source")

    op.drop_constraint(
        "fk_compliance_reports_content_version_id_content_versions",
        "compliance_reports",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_compliance_reports_generation_key", "compliance_reports", type_="unique"
    )
    op.drop_constraint(
        "uq_compliance_reports_content_version_id", "compliance_reports", type_="unique"
    )
    op.drop_column("compliance_reports", "generation_key")
    op.drop_column("compliance_reports", "input_checksum")
    op.drop_column("compliance_reports", "semantic_pass")
    op.drop_column("compliance_reports", "deterministic_pass")
    op.drop_column("compliance_reports", "prompt_revision_id")
