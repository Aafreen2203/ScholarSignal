"""Allow a limited run to resume inside an OpenAlex page and index all stored vectors."""

import sqlalchemy as sa
from alembic import op

revision = "0003_ingestion_offset_index"
down_revision = "0002_openalex_search"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ingestion_jobs",
        sa.Column("page_offset", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("DROP INDEX IF EXISTS ix_publication_embeddings_hnsw")
    op.execute("""CREATE INDEX ix_publication_embeddings_hnsw ON publication_embeddings
        USING hnsw (vector vector_cosine_ops) WHERE vector IS NOT NULL""")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_publication_embeddings_hnsw")
    op.execute("""CREATE INDEX ix_publication_embeddings_hnsw ON publication_embeddings
        USING hnsw (vector vector_cosine_ops) WHERE status = 'complete'""")
    op.drop_column("ingestion_jobs", "page_offset")
