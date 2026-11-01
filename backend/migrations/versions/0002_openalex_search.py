"""Persist OpenAlex works, ingestion checkpoints, and searchable embeddings."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002_openalex_search"
down_revision = "0001_users"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql")


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("openalex_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("abstract", sa.Text()),
        sa.Column("authors", JSON_DOCUMENT),
        sa.Column("publication_date", sa.Date()),
        sa.Column("doi", sa.String(512)),
        sa.Column("concepts", JSON_DOCUMENT),
        sa.Column("topics", JSON_DOCUMENT),
        sa.Column("cited_by_count", sa.Integer()),
        sa.Column("source", sa.String(32), nullable=False, server_default="openalex"),
        sa.Column("source_metadata", JSON_DOCUMENT, nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("openalex_id", name="uq_publications_openalex_id"),
    )
    op.create_index("ix_publications_doi", "publications", ["doi"])
    op.execute("""CREATE INDEX ix_publications_lexical ON publications USING gin
        (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, '')))""")

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_key", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="openalex"),
        sa.Column("filters", JSON_DOCUMENT, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("next_cursor", sa.Text()),
        sa.Column("pages_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("run_key", name="uq_ingestion_jobs_run_key"),
    )

    op.create_table(
        "publication_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "publication_id",
            sa.Integer(),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("vector", Vector(384)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "publication_id", "model_name", "model_version", name="uq_embedding_pub_model"
        ),
    )
    op.create_index("ix_publication_embeddings_status", "publication_embeddings", ["status"])
    op.execute("""CREATE INDEX ix_publication_embeddings_hnsw ON publication_embeddings
        USING hnsw (vector vector_cosine_ops) WHERE status = 'complete'""")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_publication_embeddings_hnsw")
    op.drop_index("ix_publication_embeddings_status", table_name="publication_embeddings")
    op.drop_table("publication_embeddings")
    op.drop_table("ingestion_jobs")
    op.execute("DROP INDEX IF EXISTS ix_publications_lexical")
    op.drop_index("ix_publications_doi", table_name="publications")
    op.drop_table("publications")
    # Keep the shared extension installed; another application table may use it.
