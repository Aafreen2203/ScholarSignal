"""Add auditable OpenAlex usage events and preserve existing aggregates."""

import sqlalchemy as sa
from alembic import op

revision = "0006_openalex_usage_events"
down_revision = "0005_openalex_usage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "openalex_usage_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("utc_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("amount_usd", sa.Numeric(16, 8), nullable=False),
        sa.Column("actual_cost_known", sa.Boolean(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_openalex_usage_events_utc_date", "openalex_usage_events", ["utc_date"]
    )
    # Preserve the old aggregate as an audit event. It cannot be decomposed into
    # request-level costs because the earlier schema retained only a total and count.
    op.execute(
        sa.text(
            """
            INSERT INTO openalex_usage_events
                (utc_date, event_type, amount_usd, actual_cost_known, details)
            SELECT utc_date, 'legacy_aggregate', project_spend_usd, false,
                   json_build_object(
                       'request_count', request_count,
                       'recorded_project_spend_usd', project_spend_usd,
                       'request_level_costs', 'unknown; prior schema stored aggregate only'
                   )
            FROM openalex_daily_usage
            WHERE request_count > 0 OR project_spend_usd > 0
            """
        )
    )


def downgrade():
    op.drop_index("ix_openalex_usage_events_utc_date", table_name="openalex_usage_events")
    op.drop_table("openalex_usage_events")
