"""Phase 2 context, knowledge freshness, and content drafts.

Revision ID: 9b21d8f6a4c2
Revises: c5d7c8bf0272
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9b21d8f6a4c2"
down_revision: str | None = "c5d7c8bf0272"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column(
        "registry_revisions",
        sa.Column(
            "verification_status",
            sa.Enum("provisional", "verified", name="verificationstatus", native_enum=False),
            nullable=False,
            server_default="provisional",
        ),
    )
    op.add_column(
        "registry_revisions",
        sa.Column(
            "usage_scope",
            sa.Enum("sandbox_only", "production", name="usagescope", native_enum=False),
            nullable=False,
            server_default="sandbox_only",
        ),
    )
    op.add_column(
        "campaign_briefs",
        sa.Column(
            "run_mode",
            sa.Enum("sandbox", "production", name="runmode", native_enum=False),
            nullable=False,
            server_default="sandbox",
        ),
    )
    op.add_column(
        "growth_runs",
        sa.Column(
            "run_mode",
            sa.Enum("sandbox", "production", name="runmode", native_enum=False),
            nullable=False,
            server_default="sandbox",
        ),
    )

    op.add_column("strategy_plans", sa.Column("prompt_revision_id", sa.Uuid(), nullable=True))
    op.add_column("strategy_plans", sa.Column("input_checksum", sa.String(64), nullable=True))
    op.add_column("strategy_plans", sa.Column("generation_key", sa.String(64), nullable=True))
    op.execute(
        "UPDATE strategy_plans SET "
        "prompt_revision_id = '00000000-0000-0000-0000-000000000000', "
        "input_checksum = repeat('0', 64), "
        "generation_key = md5(id::text) || md5(id::text)"
    )
    op.alter_column("strategy_plans", "prompt_revision_id", nullable=False)
    op.alter_column("strategy_plans", "input_checksum", nullable=False)
    op.alter_column("strategy_plans", "generation_key", nullable=False)
    op.create_unique_constraint("uq_strategy_plans_run_id", "strategy_plans", ["run_id"])
    op.create_unique_constraint(
        "uq_strategy_plans_generation_key", "strategy_plans", ["generation_key"]
    )
    op.create_foreign_key(
        "fk_strategy_plans_run_id_growth_runs",
        "strategy_plans",
        "growth_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("content_candidates", sa.Column("route_key", sa.String(100), nullable=True))
    op.execute("UPDATE content_candidates SET route_key = angle_key || '-' || left(id::text, 8)")
    op.alter_column("content_candidates", "route_key", nullable=False)
    op.create_unique_constraint(
        "uq_content_candidates_run_id", "content_candidates", ["run_id", "route_key"]
    )
    op.create_foreign_key(
        "fk_content_candidates_run_id_growth_runs",
        "content_candidates",
        "growth_runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("content_versions", sa.Column("input_checksum", sa.String(64), nullable=True))
    op.add_column("content_versions", sa.Column("generation_key", sa.String(64), nullable=True))
    op.execute(
        "UPDATE content_versions SET input_checksum = repeat('0', 64), "
        "generation_key = md5(id::text) || md5(id::text), "
        "prompt_revision_id = COALESCE(prompt_revision_id, "
        "'00000000-0000-0000-0000-000000000000')"
    )
    op.alter_column("content_versions", "prompt_revision_id", nullable=False)
    op.alter_column("content_versions", "input_checksum", nullable=False)
    op.alter_column("content_versions", "generation_key", nullable=False)
    op.create_unique_constraint(
        "uq_content_versions_generation_key", "content_versions", ["generation_key"]
    )
    op.create_foreign_key(
        "fk_content_versions_candidate_id_content_candidates",
        "content_versions",
        "content_candidates",
        ["candidate_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column(
            "retrieval_method",
            sa.Enum(
                "manual",
                "fixed_url",
                "web_search",
                "official_api",
                name="retrievalmethod",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("freshness_days", sa.Integer(), nullable=False),
        sa.Column(
            "criticality",
            sa.Enum("normal", "critical", name="knowledgecriticality", native_enum=False),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_sources"),
        sa.UniqueConstraint("brand_id", "canonical_url", name="uq_knowledge_sources_brand_id"),
    )
    op.create_index("ix_knowledge_sources_brand_id", "knowledge_sources", ["brand_id"])

    op.create_table(
        "source_captures",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("metadata_json", JSON_TYPE, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["knowledge_sources.id"], ondelete="CASCADE",
            name="fk_source_captures_source_id_knowledge_sources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_captures"),
        sa.UniqueConstraint("source_id", "checksum", name="uq_source_captures_source_id"),
    )
    op.create_index("ix_source_captures_brand_id", "source_captures", ["brand_id"])
    op.create_index("ix_source_captures_source_id", "source_captures", ["source_id"])

    op.create_table(
        "registry_verifications",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_capture_id", sa.Uuid(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "result",
            sa.Enum(
                "unchanged",
                "changed",
                "unavailable",
                "manually_verified",
                name="verificationresult",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("checked_by", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["registry_revisions.id"], ondelete="CASCADE",
            name="fk_registry_verifications_revision_id_registry_revisions",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["knowledge_sources.id"], ondelete="SET NULL",
            name="fk_registry_verifications_source_id_knowledge_sources",
        ),
        sa.ForeignKeyConstraint(
            ["source_capture_id"], ["source_captures.id"], ondelete="SET NULL",
            name="fk_registry_verifications_source_capture_id_source_captures",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_registry_verifications"),
    )
    op.create_index("ix_registry_verifications_brand_id", "registry_verifications", ["brand_id"])
    op.create_index("ix_registry_verifications_revision_id", "registry_verifications", ["revision_id"])
    op.create_index("ix_registry_verifications_source_id", "registry_verifications", ["source_id"])

    op.create_table(
        "run_context_packages",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "context_type",
            sa.Enum("product", "policy", "trend", name="contexttype", native_enum=False),
            nullable=False,
        ),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("generation_key", sa.String(64), nullable=False),
        sa.Column("prompt_revision_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["growth_runs.id"], ondelete="CASCADE",
            name="fk_run_context_packages_run_id_growth_runs",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_context_packages"),
        sa.UniqueConstraint("run_id", "context_type", name="uq_run_context_packages_run_id"),
        sa.UniqueConstraint("generation_key", name="uq_run_context_packages_generation_key"),
    )
    op.create_index("ix_run_context_packages_brand_id", "run_context_packages", ["brand_id"])
    op.create_index("ix_run_context_packages_run_id", "run_context_packages", ["run_id"])

    op.create_table(
        "content_claim_usages",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("content_version_id", sa.Uuid(), nullable=False),
        sa.Column("claim_revision_id", sa.Uuid(), nullable=False),
        sa.Column("usage_type", sa.String(30), nullable=False),
        sa.Column("content_excerpt", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_version_id"], ["content_versions.id"], ondelete="CASCADE",
            name="fk_content_claim_usages_content_version_id_content_versions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_claim_usages"),
        sa.UniqueConstraint(
            "content_version_id", "claim_revision_id", "usage_type",
            name="uq_content_claim_usages_content_version_id",
        ),
    )
    op.create_index("ix_content_claim_usages_brand_id", "content_claim_usages", ["brand_id"])
    op.create_index(
        "ix_content_claim_usages_content_version_id",
        "content_claim_usages",
        ["content_version_id"],
    )
    op.create_index(
        "ix_content_claim_usages_claim_revision_id",
        "content_claim_usages",
        ["claim_revision_id"],
    )


def downgrade() -> None:
    op.drop_table("content_claim_usages")
    op.drop_table("run_context_packages")
    op.drop_table("registry_verifications")
    op.drop_table("source_captures")
    op.drop_table("knowledge_sources")

    op.drop_constraint(
        "fk_content_versions_candidate_id_content_candidates", "content_versions", type_="foreignkey"
    )
    op.drop_constraint("uq_content_versions_generation_key", "content_versions", type_="unique")
    op.drop_column("content_versions", "generation_key")
    op.drop_column("content_versions", "input_checksum")
    op.alter_column("content_versions", "prompt_revision_id", nullable=True)

    op.drop_constraint(
        "fk_content_candidates_run_id_growth_runs", "content_candidates", type_="foreignkey"
    )
    op.drop_constraint("uq_content_candidates_run_id", "content_candidates", type_="unique")
    op.drop_column("content_candidates", "route_key")

    op.drop_constraint("fk_strategy_plans_run_id_growth_runs", "strategy_plans", type_="foreignkey")
    op.drop_constraint("uq_strategy_plans_generation_key", "strategy_plans", type_="unique")
    op.drop_constraint("uq_strategy_plans_run_id", "strategy_plans", type_="unique")
    op.drop_column("strategy_plans", "generation_key")
    op.drop_column("strategy_plans", "input_checksum")
    op.drop_column("strategy_plans", "prompt_revision_id")

    op.drop_column("growth_runs", "run_mode")
    op.drop_column("campaign_briefs", "run_mode")
    op.drop_column("registry_revisions", "usage_scope")
    op.drop_column("registry_revisions", "verification_status")
