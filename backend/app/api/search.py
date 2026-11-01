from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.search import SemanticModelUnavailable, search_publications

router = APIRouter(tags=["search"])


class SearchPublication(BaseModel):
    openalex_id: str
    title: str | None
    abstract: str | None
    authors: list[dict] | None
    publication_date: date | None
    doi: str | None
    concepts: list[dict] | None
    topics: list[dict] | None
    cited_by_count: int | None
    score: float


class SearchResponse(BaseModel):
    query: str
    retrieval_method: str
    method_explanation: str
    results: list[SearchPublication]


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1, max_length=500),
    method: Literal["lexical", "semantic"] = "lexical",
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        hits = search_publications(db, q, method, limit)
    except SemanticModelUnavailable:
        raise HTTPException(
            status_code=503, detail="Semantic search model is unavailable"
        ) from None
    explanation = (
        "PostgreSQL full-text lexical ranking over title and abstract."
        if method == "lexical"
        else "Cosine similarity between locally generated publication embeddings and the query embedding."
    )
    return SearchResponse(
        query=q,
        retrieval_method=method,
        method_explanation=explanation,
        results=[
            SearchPublication(
                openalex_id=hit.publication.openalex_id,
                title=hit.publication.title,
                abstract=hit.publication.abstract,
                authors=hit.publication.authors,
                publication_date=hit.publication.publication_date,
                doi=hit.publication.doi,
                concepts=hit.publication.concepts,
                topics=hit.publication.topics,
                cited_by_count=hit.publication.cited_by_count,
                score=hit.score,
            )
            for hit in hits
        ],
    )
