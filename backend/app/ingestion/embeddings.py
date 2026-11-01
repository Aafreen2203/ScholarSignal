import logging
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

import numpy as np
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.ingestion.text import embedding_text, embedding_text_hash
from backend.app.models import Publication, PublicationEmbedding
from backend.app.models.publication import VECTOR_DIMENSIONS

logger = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_VERSION = "fastembed-0.9.1"


class Encoder(Protocol):
    def embed(self, texts: list[str]): ...


class FastEmbedEncoder:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.model = self._load_model(model_name)

    @staticmethod
    @lru_cache(maxsize=4)
    def _load_model(model_name: str):
        from fastembed import TextEmbedding

        return TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]):
        return self.model.embed(texts)


def publication_text(publication: Publication) -> str | None:
    return embedding_text(publication.title, publication.abstract)


def generate_embeddings(
    session: Session,
    encoder: Encoder,
    *,
    model_name: str = MODEL_NAME,
    model_version: str = MODEL_VERSION,
    batch_size: int = 32,
    max_retries: int = 3,
    sleep=time.sleep,
) -> dict[str, int]:
    if not 1 <= batch_size <= 512:
        raise ValueError("batch_size must be between 1 and 512")
    processed = failed = skipped = 0
    last_publication_id = 0
    while True:
        candidates_filter = or_(
            PublicationEmbedding.id.is_(None),
            PublicationEmbedding.status.in_(["pending", "generating", "failed"]),
            and_(
                PublicationEmbedding.status == "skipped",
                Publication.embedding_text_hash != PublicationEmbedding.content_hash,
            ),
            and_(
                PublicationEmbedding.status == "complete",
                or_(
                    Publication.embedding_text_hash != PublicationEmbedding.content_hash,
                    PublicationEmbedding.vector.is_(None),
                ),
            ),
        )
        pairs = session.execute(
            select(Publication, PublicationEmbedding)
            .outerjoin(
                PublicationEmbedding,
                and_(
                    PublicationEmbedding.publication_id == Publication.id,
                    PublicationEmbedding.model_name == model_name,
                    PublicationEmbedding.model_version == model_version,
                ),
            )
            .where(Publication.id > last_publication_id, candidates_filter)
            .order_by(Publication.id)
            .limit(batch_size)
        ).all()
        if not pairs:
            break
        last_publication_id = pairs[-1][0].id
        candidates = []
        for publication, row in pairs:
            text = publication_text(publication)
            if text is None:
                digest = embedding_text_hash(None)
                if row is None:
                    row = PublicationEmbedding(
                        publication_id=publication.id,
                        model_name=model_name,
                        model_version=model_version,
                        dimensions=VECTOR_DIMENSIONS,
                        content_hash=digest,
                        status="skipped",
                        last_error="No title or abstract text is available.",
                    )
                    session.add(row)
                    skipped += 1
                elif row.status != "skipped" or row.content_hash != digest:
                    row.content_hash, row.vector = digest, None
                    row.status, row.last_error = (
                        "skipped",
                        "No title or abstract text is available.",
                    )
                    skipped += 1
                continue
            digest = embedding_text_hash(text)
            if row and row.status == "complete" and row.content_hash == digest:
                continue
            if row is None:
                row = PublicationEmbedding(
                    publication_id=publication.id,
                    model_name=model_name,
                    model_version=model_version,
                    dimensions=VECTOR_DIMENSIONS,
                    content_hash=digest,
                    status="pending",
                )
                session.add(row)
            row.content_hash = digest
            row.status = "generating"
            row.attempts = (row.attempts or 0) + 1
            row.last_error = None
            candidates.append((publication, row, text))
        session.commit()
        if not candidates:
            continue
        try:
            vectors = None
            error = None
            for attempt in range(max_retries + 1):
                try:
                    vectors = list(encoder.embed([text for _, _, text in candidates]))
                    break
                except (
                    Exception
                ) as exc:  # the failure is persisted below; no synthetic vector is substituted
                    error = exc
                    if attempt >= max_retries:
                        break
                    sleep(min(30.0, 2.0**attempt))
            if vectors is None or len(vectors) != len(candidates):
                message = str(error)[:1000] if error else "encoder returned a mismatched batch"
                for _, row, _ in candidates:
                    row.status, row.last_error = "failed", message
                session.commit()
                failed += len(candidates)
                break
            if any(np.asarray(vector).shape != (VECTOR_DIMENSIONS,) for vector in vectors):
                for _, row, _ in candidates:
                    row.status, row.last_error = (
                        "failed",
                        f"encoder must return {VECTOR_DIMENSIONS}-dimensional vectors",
                    )
                session.commit()
                failed += len(candidates)
                break
            for (_, row, _), vector in zip(candidates, vectors, strict=True):
                row.vector = np.asarray(vector, dtype=np.float32).tolist()
                row.status, row.last_error = "complete", None
                row.generated_at = datetime.now(UTC)
                row.updated_at = datetime.now(UTC)
            session.commit()
            processed += len(candidates)
        except Exception:
            session.rollback()
            raise
    return {"generated": processed, "failed": failed, "skipped_missing_text": skipped}
