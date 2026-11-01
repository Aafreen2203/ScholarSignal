"""Persist OpenAlex rate-limit snapshots and per-UTC-day project spend."""

import sqlalchemy as sa
from alembic import op

revision = "0005_openalex_usage"
down_revision = "0004_embedding_source_hash"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "openalex_daily_usage",
        sa.Column("utc_date", sa.Date(), primary_key=True),
        sa.Column("daily_limit_credits", sa.Numeric(16, 4), nullable=True),
        sa.Column("remaining_credits", sa.Numeric(16, 4), nullable=True),
        sa.Column("last_credits_used", sa.Numeric(16, 4), nullable=True),
        sa.Column("reset_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "project_spend_usd", sa.Numeric(16, 8), nullable=False, server_default="0"
        ),
        sa.Column("reserved_usd", sa.Numeric(16, 8), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_table("openalex_daily_usage")
