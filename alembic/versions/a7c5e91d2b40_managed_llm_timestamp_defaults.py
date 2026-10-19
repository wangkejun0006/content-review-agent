"""Add managed LLM timestamp defaults.

Revision ID: a7c5e91d2b40
Revises: 9a4f3c2d7e11
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c5e91d2b40"
down_revision: str | None = "9a4f3c2d7e11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("llm_provider_configs", "agent_llm_bindings")


def upgrade() -> None:
    for table_name in TABLES:
        op.alter_column(table_name, "created_at", server_default=sa.func.now())
        op.alter_column(table_name, "updated_at", server_default=sa.func.now())


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.alter_column(table_name, "updated_at", server_default=None)
        op.alter_column(table_name, "created_at", server_default=None)
