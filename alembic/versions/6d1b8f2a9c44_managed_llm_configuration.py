"""Managed encrypted LLM configuration.

Revision ID: 6d1b8f2a9c44
Revises: 4a8c2d61e903
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6d1b8f2a9c44"
down_revision: str | None = "4a8c2d61e903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_configs",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("default_model", sa.String(200), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(30), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "name"),
    )
    op.create_index("ix_llm_provider_configs_brand_id", "llm_provider_configs", ["brand_id"])
    op.create_table(
        "agent_llm_bindings",
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("provider_config_id", sa.Uuid(), nullable=False),
        sa.Column("model_override", sa.String(200), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_config_id"],
            ["llm_provider_configs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "purpose"),
    )
    op.create_index("ix_agent_llm_bindings_brand_id", "agent_llm_bindings", ["brand_id"])
    op.create_index(
        "ix_agent_llm_bindings_provider_config_id",
        "agent_llm_bindings",
        ["provider_config_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_llm_bindings")
    op.drop_table("llm_provider_configs")
