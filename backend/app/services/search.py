import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import and_, func, literal_column, or_, select, text
from sqlalchemy.orm import Session

from backend.app.ingestion.embeddings import MODEL_NAME, MODEL_VERSION, FastEmbedEncoder
from backend.app.models import Publication, PublicationEmbedding


class SemanticModelUnavailable(RuntimeError):
    """The real model or its model artifacts could not be loaded."""


@dataclass
class SearchHit:
    publication: Publication
    score: float


def search_publications(
    session: Session, query: str, method: str, limit: int = 10
) -> list[SearchHit]:
    query = query.strip()
    if not query:
        return []
    if method == "lexical":
        if session.bind and session.bind.dialect.name == "postgresql":
            document = text(
                "to_tsvector('english', coalesce(publications.title, '') || ' ' || coalesce(publications.abstract, ''))"
            )
            terms = func.websearch_to_tsquery(literal_column("'english'"), query)
            score = func.ts_rank_cd(document, terms)
            rows = session.execute(
                select(Publication, score.label("score"))
                    .where(
                        text(
                            "to_tsvector('english', coalesce(publications.title, '') || ' ' || "
                            "coalesce(publications.abstract, '')) @@ websearch_to_tsquery('english', :search_query)"
                        )
                    )
                .order_by(score.desc(), Publication.id)
                .limit(limit)
                    .params(search_query=query)
            ).all()
            hits = [SearchHit(pub, float(rank)) for pub, rank in rows]
        else:
            terms = re.findall(r"[\w]+", query)
            conditions = [
                or_(Publication.title.ilike(f"%{term}%"), Publication.abstract.ilike(f"%{term}%"))
                for term in terms
            ]
            pubs = session.scalars(
                select(Publication).where(and_(*conditions)).order_by(Publication.id).limit(limit)
            ).all()
            hits = [SearchHit(pub, 1.0) for pub in pubs]
    elif method == "semantic":
        try:
            vector = next(iter(FastEmbedEncoder(MODEL_NAME).embed([query])))
        except Exception as exc:
            raise SemanticModelUnavailable("The configured embedding model is unavailable") from exc
        values = np.asarray(vector, dtype=np.float32)
        if values.shape != (384,):
            raise RuntimeError("Embedding model returned an unexpected vector dimension")
        if session.bind and session.bind.dialect.name == "postgresql":
            distance = PublicationEmbedding.vector.cosine_distance(values.tolist())
            rows = session.execute(
                select(Publication, distance.label("distance"))
                .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
                .where(
                    PublicationEmbedding.model_name == MODEL_NAME,
                    PublicationEmbedding.model_version == MODEL_VERSION,
                    PublicationEmbedding.status == "complete",
                    PublicationEmbedding.vector.is_not(None),
                )
                .order_by(distance, Publication.id)
                .limit(limit)
            ).all()
            hits = [SearchHit(pub, 1.0 - float(distance_value)) for pub, distance_value in rows]
        else:
            rows = session.execute(
                select(Publication, PublicationEmbedding.vector)
                .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
                .where(
                    PublicationEmbedding.model_name == MODEL_NAME,
                    PublicationEmbedding.model_version == MODEL_VERSION,
                    PublicationEmbedding.status == "complete",
                )
            ).all()
            ranked = []
            norm = float(np.linalg.norm(values))
            for publication, stored in rows:
                stored_vector = np.asarray(stored, dtype=np.float32)
                score = float(
                    np.dot(values, stored_vector) / (norm * np.linalg.norm(stored_vector))
                )
                ranked.append(SearchHit(publication, score))
            hits = sorted(ranked, key=lambda hit: (-hit.score, hit.publication.id))[:limit]
    else:
        raise ValueError("method must be lexical or semantic")
    return hits
