"""Remove sandbox/production runtime split.

Revision ID: d8a4f6c1e2b7
Revises: c2f9a61e7d84
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8a4f6c1e2b7"
down_revision: str | None = "c2f9a61e7d84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE registry_revisions
            SET verification_status = 'verified'
            WHERE item_id IN (
                SELECT id FROM registry_items WHERE registry_type = 'platform_rule'
            )
            """
        )
    )
    with op.batch_alter_table("campaign_briefs") as batch:
        batch.drop_column("run_mode")
    with op.batch_alter_table("growth_runs") as batch:
        batch.drop_column("run_mode")
    with op.batch_alter_table("registry_revisions") as batch:
        batch.drop_column("usage_scope")


def downgrade() -> None:
    with op.batch_alter_table("registry_revisions") as batch:
        batch.add_column(
            sa.Column(
                "usage_scope",
                sa.Enum(
                    "sandbox_only",
                    "production",
                    name="usagescope",
                    native_enum=False,
                ),
                nullable=False,
                server_default="production",
            )
        )
    with op.batch_alter_table("growth_runs") as batch:
        batch.add_column(
            sa.Column(
                "run_mode",
                sa.Enum("sandbox", "production", name="runmode", native_enum=False),
                nullable=False,
                server_default="production",
            )
        )
    with op.batch_alter_table("campaign_briefs") as batch:
        batch.add_column(
            sa.Column(
                "run_mode",
                sa.Enum("sandbox", "production", name="runmode", native_enum=False),
                nullable=False,
                server_default="production",
            )
        )
