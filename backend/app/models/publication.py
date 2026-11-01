from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

VECTOR_DIMENSIONS = 384
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    openalex_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    embedding_text_hash: Mapped[str | None] = mapped_column(String(64))
    authors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON_DOCUMENT)
    publication_date: Mapped[date | None] = mapped_column(Date)
    doi: Mapped[str | None] = mapped_column(String(512), index=True)
    concepts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON_DOCUMENT)
    topics: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON_DOCUMENT)
    cited_by_count: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="openalex")
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    embedding: Mapped["PublicationEmbedding | None"] = relationship(back_populates="publication")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="openalex")
    filters: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    next_cursor: Mapped[str | None] = mapped_column(Text)
    page_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublicationEmbedding(Base):
    __tablename__ = "publication_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "publication_id", "model_name", "model_version", name="uq_embedding_pub_model"
        ),
        Index("ix_publication_embeddings_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    publication_id: Mapped[int] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    vector: Mapped[list[float] | None] = mapped_column(
        Vector(VECTOR_DIMENSIONS).with_variant(JSON(), "sqlite")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    publication: Mapped[Publication] = relationship(back_populates="embedding")
