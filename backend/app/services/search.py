import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import String, and_, cast, func, literal_column, or_, select, text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.ingestion.embeddings import FastEmbedEncoder
from backend.app.models import Publication, PublicationEmbedding


class SemanticModelUnavailable(RuntimeError):
    """The real model or its model artifacts could not be loaded."""


@dataclass
class SearchHit:
    publication: Publication
    score: float
    explanation: str | None = None


@dataclass
class SearchPage:
    hits: list[SearchHit]
    total: int
    capped: bool = False


def _filter_conditions(filters: dict[str, Any] | None):
    filters = filters or {}
    conditions = []
    year_from, year_to = filters.get("year_from"), filters.get("year_to")
    if year_from:
        conditions.append(Publication.publication_date >= date(int(year_from), 1, 1))
    if year_to:
        conditions.append(Publication.publication_date <= date(int(year_to), 12, 31))
    author = filters.get("author")
    if author:
        escaped = str(author).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(cast(Publication.authors, String).ilike(f"%{escaped}%", escape="\\"))
    topic = filters.get("topic")
    if topic:
        escaped = str(topic).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            or_(
                cast(Publication.topics, String).ilike(f"%{escaped}%", escape="\\"),
                cast(Publication.concepts, String).ilike(f"%{escaped}%", escape="\\"),
            )
        )
    return conditions


def _publication_order(sort_by: str, score=None):
    if sort_by == "date":
        return [Publication.publication_date.desc().nullslast(), Publication.id]
    if sort_by == "citations":
        return [Publication.cited_by_count.desc().nullslast(), Publication.id]
    if score is not None:
        return [score.desc(), Publication.id]
    return [Publication.id]


def _lexical(session: Session, query: str, filters, *, limit: int, offset: int, sort_by: str):
    conditions = _filter_conditions(filters)
    if session.bind and session.bind.dialect.name == "postgresql":
        document = text(
            "to_tsvector('english', coalesce(publications.title, '') || ' ' || coalesce(publications.abstract, ''))"
        )
        query_expr = func.websearch_to_tsquery(literal_column("'english'"), query)
        match = text(
            "to_tsvector('english', coalesce(publications.title, '') || ' ' || "
            "coalesce(publications.abstract, '')) @@ websearch_to_tsquery('english', :search_query)"
        )
        conditions.append(match)
        score = func.ts_rank_cd(document, query_expr)
        total = (
            session.scalar(
                select(func.count())
                .select_from(Publication)
                .where(*conditions)
                .params(search_query=query)
            )
            or 0
        )
        rows = session.execute(
            select(Publication, score.label("score"))
            .where(*conditions)
            .order_by(*_publication_order(sort_by, score))
            .limit(limit)
            .offset(offset)
            .params(search_query=query)
        ).all()
        return SearchPage([SearchHit(pub, float(rank), "Lexical title/abstract match") for pub, rank in rows], total)

    terms = re.findall(r"[\w]+", query)
    conditions.extend(
        or_(Publication.title.ilike(f"%{term}%"), Publication.abstract.ilike(f"%{term}%"))
        for term in terms
    )
    base = select(Publication).where(and_(*conditions))
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    pubs = session.scalars(
        base.order_by(*_publication_order(sort_by)).limit(limit).offset(offset)
    ).all()
    return SearchPage([SearchHit(pub, 1.0, "Lexical title/abstract match") for pub in pubs], total)


def _semantic_candidates(session: Session, query: str, filters, *, limit: int):
    values = _query_vector(query)
    conditions = _embedding_conditions(filters)
    if session.bind and session.bind.dialect.name == "postgresql":
        distance = PublicationEmbedding.vector.cosine_distance(values.tolist())
        rows = session.execute(
            select(Publication, distance.label("distance"))
            .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
            .where(*conditions)
            .order_by(distance, Publication.id)
            .limit(limit)
        ).all()
        return [SearchHit(pub, 1.0 - float(distance), "Semantic cosine similarity") for pub, distance in rows]

    rows = session.execute(
        select(Publication, PublicationEmbedding.vector)
        .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
        .where(*conditions)
    ).all()
    ranked = []
    norm = float(np.linalg.norm(values))
    for publication, stored in rows:
        stored_vector = np.asarray(stored, dtype=np.float32)
        denominator = norm * float(np.linalg.norm(stored_vector))
        score = float(np.dot(values, stored_vector) / denominator) if denominator else 0.0
        ranked.append(SearchHit(publication, score, "Semantic cosine similarity"))
    return sorted(ranked, key=lambda hit: (-hit.score, hit.publication.id))[:limit]


def _query_vector(query: str) -> np.ndarray:
    try:
        vector = next(iter(FastEmbedEncoder(get_settings().embedding_model_name).embed([query])))
    except Exception as exc:
        raise SemanticModelUnavailable("The configured embedding model is unavailable") from exc
    values = np.asarray(vector, dtype=np.float32)
    if values.shape != (384,) or not np.isfinite(values).all():
        raise RuntimeError("Embedding model returned an invalid query vector")

    return values


def _embedding_conditions(filters):
    settings = get_settings()
    return [
        PublicationEmbedding.model_name == settings.embedding_model_name,
        PublicationEmbedding.model_version == settings.embedding_model_version,
        PublicationEmbedding.status == "complete",
        PublicationEmbedding.vector.is_not(None),
        *_filter_conditions(filters),
    ]


def _semantic_total(session: Session, filters):
    return int(
        session.scalar(
            select(func.count())
            .select_from(PublicationEmbedding)
            .join(Publication, Publication.id == PublicationEmbedding.publication_id)
            .where(*_embedding_conditions(filters))
        )
        or 0
    )


def _semantic_page(session, query, filters, *, limit, offset, sort_by):
    values = _query_vector(query)
    conditions = _embedding_conditions(filters)
    total = _semantic_total(session, filters)
    if session.bind and session.bind.dialect.name == "postgresql":
        distance = PublicationEmbedding.vector.cosine_distance(values.tolist())
        ordering = [distance, Publication.id] if sort_by == "relevance" else _publication_order(sort_by)
        rows = session.execute(
            select(Publication, distance.label("distance"))
            .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
            .where(*conditions)
            .order_by(*ordering)
            .offset(offset)
            .limit(limit)
        ).all()
        return SearchPage(
            [SearchHit(pub, 1.0 - float(distance), "Semantic cosine similarity") for pub, distance in rows],
            total,
        )

    rows = session.execute(
        select(Publication, PublicationEmbedding.vector)
        .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
        .where(*conditions)
    ).all()
    ranked = []
    norm = float(np.linalg.norm(values))
    for publication, stored in rows:
        stored_vector = np.asarray(stored, dtype=np.float32)
        denominator = norm * float(np.linalg.norm(stored_vector))
        score = float(np.dot(values, stored_vector) / denominator) if denominator else 0.0
        ranked.append(SearchHit(publication, score, "Semantic cosine similarity"))
    if sort_by == "date":
        ranked.sort(key=lambda hit: (hit.publication.publication_date is not None, hit.publication.publication_date or date.min), reverse=True)
    elif sort_by == "citations":
        ranked.sort(key=lambda hit: (hit.publication.cited_by_count is not None, hit.publication.cited_by_count or 0), reverse=True)
    else:
        ranked.sort(key=lambda hit: (-hit.score, hit.publication.id))
    return SearchPage(ranked[offset : offset + limit], total)


def search_publications_page(
    session: Session,
    query: str,
    method: str,
    *,
    limit: int = 10,
    offset: int = 0,
    filters: dict[str, Any] | None = None,
    sort_by: str = "relevance",
) -> SearchPage:
    query = query.strip()
    if not query:
        return SearchPage([], 0)
    if method not in {"lexical", "semantic", "hybrid"}:
        raise ValueError("method must be lexical, semantic, or hybrid")
    if sort_by not in {"relevance", "date", "citations"}:
        raise ValueError("sort_by must be relevance, date, or citations")
    if method == "lexical":
        return _lexical(session, query, filters, limit=limit, offset=offset, sort_by=sort_by)
    if method == "semantic":
        return _semantic_page(
            session, query, filters, limit=limit, offset=offset, sort_by=sort_by
        )
    # Reciprocal Rank Fusion combines two transparent candidate lists; the 100-per-
    # method window bounds work and is surfaced in the explanation.
    candidate_cap = min(1000, max(100, offset + limit))
    lexical = _lexical(session, query, filters, limit=candidate_cap, offset=0, sort_by="relevance")
    semantic = _semantic_candidates(session, query, filters, limit=candidate_cap)
    was_capped = lexical.total > candidate_cap or _semantic_total(session, filters) > candidate_cap
    fused: dict[int, tuple[SearchHit, float, list[str]]] = {}
    for hits, label in ((lexical.hits, "lexical"), (semantic, "semantic")):
        for rank, hit in enumerate(hits, start=1):
            key = hit.publication.id
            current = fused.get(key)
            score = 1.0 / (60 + rank)
            if current is None:
                fused[key] = (hit, score, [label])
            else:
                fused[key] = (current[0], current[1] + score, current[2] + [label])
    ranked = [
        SearchHit(hit.publication, score, "Hybrid RRF: " + " + ".join(labels))
        for hit, score, labels in fused.values()
    ]
    if sort_by == "date":
        ranked.sort(
            key=lambda h: h.publication.publication_date or date.min, reverse=True
        )
    elif sort_by == "citations":
        ranked.sort(
            key=lambda h: (
                h.publication.cited_by_count is not None,
                h.publication.cited_by_count or 0,
            ),
            reverse=True,
        )
    else:
        ranked.sort(key=lambda h: (-h.score, h.publication.id))
    ranked = ranked[:candidate_cap]
    return SearchPage(ranked[offset : offset + limit], len(ranked), was_capped)


def search_publications(
    session: Session, query: str, method: str, limit: int = 10
) -> list[SearchHit]:
    """Backwards-compatible list-returning search entry point."""
    return search_publications_page(session, query, method, limit=limit).hits
