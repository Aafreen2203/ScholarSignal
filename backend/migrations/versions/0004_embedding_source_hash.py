"""Track the normalized embedding input hash on each publication."""

import sqlalchemy as sa
from alembic import op

revision = "0004_embedding_source_hash"
down_revision = "0003_ingestion_offset_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("publications", sa.Column("embedding_text_hash", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("publications", "embedding_text_hash")
