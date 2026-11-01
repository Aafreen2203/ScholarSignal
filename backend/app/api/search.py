from datetime import UTC, date, datetime
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import optional_current_user
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models import (
    Publication,
    PublicationEmbedding,
    PublicationView,
    SearchHistory,
    User,
)
from backend.app.services.search import (
    SemanticModelUnavailable,
    search_publications_page,
)

router = APIRouter(tags=["search"])
SEARCH_HISTORY_RETENTION = 200


class SearchPublication(BaseModel):
    id: int
    openalex_id: str
    title: str | None
    abstract: str | None
    authors: list[dict[str, Any]] | None
    publication_date: date | None
    doi: str | None
    concepts: list[dict[str, Any]] | None
    topics: list[dict[str, Any]] | None
    cited_by_count: int | None
    score: float
    explanation: str | None = None


class SearchResponse(BaseModel):
    query: str
    retrieval_method: str
    method_explanation: str
    results: list[SearchPublication]
    total: int
    results_capped: bool
    page: int
    per_page: int
    sort_by: str


class PublicationDetail(SearchPublication):
    source: str
    retrieved_at: datetime
    venue: str | None = None
    references: list[str]


class RelatedResponse(BaseModel):
    publication_id: int
    retrieval_method: str
    method_explanation: str
    results: list[SearchPublication]


class SearchHistoryItem(BaseModel):
    id: int
    query: str
    method: str
    filters: dict[str, Any]
    result_count: int
    created_at: datetime


def _venue(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    location = metadata.get("primary_location")
    source = location.get("source") if isinstance(location, dict) else None
    name = source.get("display_name") if isinstance(source, dict) else None
    return name if isinstance(name, str) else None


def _references(metadata: Any) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    raw = metadata.get("referenced_works")
    if not isinstance(raw, list):
        return []
    return [item for item in raw[:50] if isinstance(item, str) and item.startswith("https://openalex.org/")]


def _publication_result(hit):
    publication = hit.publication
    return SearchPublication(
        id=publication.id,
        openalex_id=publication.openalex_id,
        title=publication.title,
        abstract=publication.abstract,
        authors=publication.authors,
        publication_date=publication.publication_date,
        doi=publication.doi,
        concepts=publication.concepts,
        topics=publication.topics,
        cited_by_count=publication.cited_by_count,
        score=hit.score,
        explanation=hit.explanation,
    )


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1, max_length=500),
    method: Literal["lexical", "semantic", "hybrid"] = "lexical",
    page: int = Query(default=1, ge=1, le=100),
    per_page: int = Query(default=10, ge=1, le=50),
    sort_by: Literal["relevance", "date", "citations"] = "relevance",
    year_from: int | None = Query(default=None, ge=1800, le=date.today().year + 1),
    year_to: int | None = Query(default=None, ge=1800, le=date.today().year + 1),
    author: str | None = Query(default=None, min_length=1, max_length=200),
    topic: str | None = Query(default=None, min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
):
    if year_from and year_to and year_from > year_to:
        raise HTTPException(status_code=422, detail="year_from must not exceed year_to")
    normalized_query = q.strip()
    if not normalized_query:
        raise HTTPException(status_code=422, detail="q cannot be blank")
    normalized_author = author.strip() if author else None
    normalized_topic = topic.strip() if topic else None
    if author is not None and not normalized_author:
        raise HTTPException(status_code=422, detail="author cannot be blank")
    if topic is not None and not normalized_topic:
        raise HTTPException(status_code=422, detail="topic cannot be blank")
    filters = {
        key: value
        for key, value in {
            "year_from": year_from,
            "year_to": year_to,
            "author": normalized_author,
            "topic": normalized_topic,
        }.items()
        if value is not None
    }
    try:
        result_page = search_publications_page(
            db,
            normalized_query,
            method,
            limit=per_page,
            offset=(page - 1) * per_page,
            filters=filters,
            sort_by=sort_by,
        )
    except SemanticModelUnavailable:
        raise HTTPException(status_code=503, detail="Semantic search model is unavailable") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    method_explanations = {
        "lexical": "PostgreSQL English full-text ranking over titles and abstracts.",
        "semantic": "Cosine similarity between local publication and query embeddings.",
        "hybrid": "Reciprocal Rank Fusion of lexical and semantic candidates (up to 1,000 per method); results_capped identifies a truncated candidate set.",
    }
    if user is not None:
        db.add(
            SearchHistory(
                owner_id=user.id,
                query=normalized_query,
                method=method,
                filters=filters,
                result_count=result_page.total,
            )
        )
        db.flush()
        retained_ids = (
            select(SearchHistory.id)
            .where(SearchHistory.owner_id == user.id)
            .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
            .limit(SEARCH_HISTORY_RETENTION)
        )
        db.execute(
            delete(SearchHistory)
            .where(
                SearchHistory.owner_id == user.id,
                SearchHistory.id.not_in(retained_ids),
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
    return SearchResponse(
        query=normalized_query,
        retrieval_method=method,
        method_explanation=method_explanations[method],
        results=[_publication_result(hit) for hit in result_page.hits],
        total=result_page.total,
        results_capped=result_page.capped,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
    )


@router.get("/publications/{publication_id}", response_model=PublicationDetail)
def publication_detail(
    publication_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    if user is not None:
        view = db.scalar(
            select(PublicationView).where(
                PublicationView.owner_id == user.id,
                PublicationView.publication_id == publication.id,
            )
        )
        now = datetime.now(UTC)
        if view is None:
            view = PublicationView(owner_id=user.id, publication_id=publication.id)
            db.add(view)
        else:
            view.viewed_at = now
        db.commit()
    return PublicationDetail(
        id=publication.id,
        openalex_id=publication.openalex_id,
        title=publication.title,
        abstract=publication.abstract,
        authors=publication.authors,
        publication_date=publication.publication_date,
        doi=publication.doi,
        concepts=publication.concepts,
        topics=publication.topics,
        cited_by_count=publication.cited_by_count,
        score=0,
        source=publication.source,
        retrieved_at=publication.retrieved_at,
        venue=_venue(publication.source_metadata),
        references=_references(publication.source_metadata),
    )


@router.get("/publications/{publication_id}/related", response_model=RelatedResponse)
def related_publications(
    publication_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    settings = get_settings()
    embedding = db.scalar(
        select(PublicationEmbedding).where(
            PublicationEmbedding.publication_id == publication_id,
            PublicationEmbedding.model_name == settings.embedding_model_name,
            PublicationEmbedding.model_version == settings.embedding_model_version,
            PublicationEmbedding.status == "complete",
            PublicationEmbedding.vector.is_not(None),
        )
    )
    if embedding is None:
        raise HTTPException(status_code=409, detail="A current semantic embedding is unavailable")
    conditions = (
        PublicationEmbedding.model_name == settings.embedding_model_name,
        PublicationEmbedding.model_version == settings.embedding_model_version,
        PublicationEmbedding.status == "complete",
        PublicationEmbedding.vector.is_not(None),
        Publication.id != publication_id,
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        distance = PublicationEmbedding.vector.cosine_distance(embedding.vector)
        rows = db.execute(
            select(Publication, distance.label("distance"))
            .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
            .where(*conditions)
            .order_by(distance, Publication.id)
            .limit(limit)
        ).all()
        results = [
            SearchPublication(
                id=pub.id,
                openalex_id=pub.openalex_id,
                title=pub.title,
                abstract=pub.abstract,
                authors=pub.authors,
                publication_date=pub.publication_date,
                doi=pub.doi,
                concepts=pub.concepts,
                topics=pub.topics,
                cited_by_count=pub.cited_by_count,
                score=1.0 - float(distance_value),
                explanation="Local embedding cosine similarity to the source publication",
            )
            for pub, distance_value in rows
        ]
    else:
        rows = db.execute(
            select(Publication, PublicationEmbedding.vector)
            .join(PublicationEmbedding, PublicationEmbedding.publication_id == Publication.id)
            .where(*conditions)
        ).all()
        target = np.asarray(embedding.vector, dtype=np.float32)
        ranked = []
        for candidate, vector in rows:
            values = np.asarray(vector, dtype=np.float32)
            denominator = float(np.linalg.norm(target) * np.linalg.norm(values))
            score = float(np.dot(target, values) / denominator) if denominator else 0.0
            ranked.append((candidate, score))
        ranked.sort(key=lambda item: (-item[1], item[0].id))
        results = [
            SearchPublication(
                id=pub.id,
                openalex_id=pub.openalex_id,
                title=pub.title,
                abstract=pub.abstract,
                authors=pub.authors,
                publication_date=pub.publication_date,
                doi=pub.doi,
                concepts=pub.concepts,
                topics=pub.topics,
                cited_by_count=pub.cited_by_count,
                score=score,
                explanation="Local embedding cosine similarity to the source publication",
            )
            for pub, score in ranked[:limit]
        ]
    return RelatedResponse(
        publication_id=publication_id,
        retrieval_method="semantic_similarity",
        method_explanation="Nearest stored FastEmbed vectors; no external model or API request was used.",
        results=results,
    )


@router.get("/search/history", response_model=list[SearchHistoryItem])
def search_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(optional_current_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    rows = db.scalars(
        select(SearchHistory)
        .where(SearchHistory.owner_id == user.id)
        .order_by(SearchHistory.created_at.desc(), SearchHistory.id.desc())
        .limit(limit)
    ).all()
    return [
        SearchHistoryItem(
            id=row.id,
            query=row.query,
            method=row.method,
            filters=row.filters,
            result_count=row.result_count,
            created_at=row.created_at,
        )
        for row in rows
    ]
