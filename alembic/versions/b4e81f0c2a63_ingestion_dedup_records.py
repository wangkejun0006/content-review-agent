"""Add governed AI ingestion dedup records.

Revision ID: b4e81f0c2a63
Revises: a7c5e91d2b40
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e81f0c2a63"
down_revision: str | None = "a7c5e91d2b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_records",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_type", sa.String(50), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("duplicate_status", sa.String(20), nullable=False, server_default="none"),
        sa.Column("matches", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="awaiting_decision"),
        sa.Column("decision", sa.String(30), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("resulting_item_id", sa.Uuid(), nullable=True),
        sa.Column("resulting_revision_id", sa.Uuid(), nullable=True),
        sa.Column("resulting_evidence_document_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_records_brand_id", "ingestion_records", ["brand_id"])
    op.create_index(
        "ix_ingestion_records_source",
        "ingestion_records",
        ["brand_id", "ingestion_type", "source_checksum"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_records_source", table_name="ingestion_records")
    op.drop_index("ix_ingestion_records_brand_id", table_name="ingestion_records")
    op.drop_table("ingestion_records")
