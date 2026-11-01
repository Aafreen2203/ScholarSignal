"""Add private collections, saved publications, notes, views and search history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_research_workspace"
down_revision = "0006_openalex_usage_events"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "research_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_collection_owner_name"),
    )
    op.create_index("ix_research_collections_owner_id", "research_collections", ["owner_id"])

    op.create_table(
        "saved_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "publication_id", name="uq_saved_owner_publication"),
    )
    op.create_index("ix_saved_publications_owner_id", "saved_publications", ["owner_id"])
    op.create_index("ix_saved_publications_publication_id", "saved_publications", ["publication_id"])

    op.create_table(
        "collection_publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("research_collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("collection_id", "publication_id", name="uq_collection_publication"),
    )
    op.create_index("ix_collection_publications_collection_id", "collection_publications", ["collection_id"])
    op.create_index("ix_collection_publications_publication_id", "collection_publications", ["publication_id"])

    op.create_table(
        "research_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_research_notes_owner_id", "research_notes", ["owner_id"])
    op.create_index("ix_research_notes_publication_id", "research_notes", ["publication_id"])
    op.create_index("ix_research_notes_owner_updated", "research_notes", ["owner_id", "updated_at"])

    op.create_table(
        "search_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("filters", JSON_DOCUMENT, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_search_history_owner_id", "search_history", ["owner_id"])
    op.create_index("ix_search_history_owner_created", "search_history", ["owner_id", "created_at"])

    op.create_table(
        "publication_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "publication_id", name="uq_view_owner_publication"),
    )
    op.create_index("ix_publication_views_owner_viewed", "publication_views", ["owner_id", "viewed_at"])


def downgrade():
    op.drop_table("publication_views")
    op.drop_table("search_history")
    op.drop_table("research_notes")
    op.drop_table("collection_publications")
    op.drop_table("saved_publications")
    op.drop_table("research_collections")
