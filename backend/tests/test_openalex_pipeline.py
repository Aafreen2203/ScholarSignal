import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import SessionLocal, get_db
from backend.app.ingestion.embeddings import generate_embeddings
from backend.app.ingestion.openalex import (
    OpenAlexClient,
    OpenAlexIngestor,
    normalize_work,
    reconstruct_abstract,
    run_key,
    upsert_page,
)
from backend.app.main import app
from backend.app.models import IngestionJob, Publication, PublicationEmbedding
from backend.app.services.search import search_publications


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with sessions() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def work(work_id="https://openalex.org/W100", *, cited_by_count=0, abstract=True):
    return {
        "id": work_id,
        "title": "Real fixtures are not OpenAlex data",
        "publication_date": "2024-03-12",
        "doi": "https://doi.org/10.5555/example",
        "authorships": [
            {"author": {"id": "https://openalex.org/A1", "display_name": "Test Author"}}
        ],
        "concepts": [
            {"id": "https://openalex.org/C1", "display_name": "Test concept", "score": 0.5}
        ],
        "topics": [],
        **({"cited_by_count": cited_by_count} if cited_by_count is not None else {}),
        **(
            {"abstract_inverted_index": {"Research": [0], "fixture": [1], "text": [2]}}
            if abstract
            else {}
        ),
    }


def test_cursor_pagination_retries_and_resumes_inside_limited_page(database):
    calls = []

    class FakeOpenAlex:
        def fetch_page(self, *, cursor, filters):
            calls.append((cursor, filters))
            if cursor == "*":
                return {
                    "results": [work(), work("https://openalex.org/W101")],
                    "meta": {"next_cursor": "next"},
                }
            return {"results": [work("https://openalex.org/W102")], "meta": {"next_cursor": None}}

    filters = {"filter": "publication_year:2024"}
    ingestor = OpenAlexIngestor(database, FakeOpenAlex())
    job = ingestor.ingest(filters=filters, limit=1)
    assert job.status == "paused"
    assert job.next_cursor == "*" and job.page_offset == 1
    assert database.scalar(select(func.count()).select_from(Publication)) == 1
    job = ingestor.ingest(filters=filters, limit=1)
    assert job.status == "paused"
    assert job.next_cursor == "next" and job.page_offset == 0
    job = ingestor.ingest(filters=filters, limit=5)
    assert job.status == "complete"
    assert job.pages_processed == 2
    assert database.scalar(select(func.count()).select_from(Publication)) == 3
    # A completed filter can be refreshed safely without duplicate source IDs.
    refreshed = ingestor.ingest(filters=filters, limit=5)
    assert refreshed.status == "complete"
    assert database.scalar(select(func.count()).select_from(Publication)) == 3
    assert [cursor for cursor, _ in calls] == ["*", "*", "next", "*", "next"]


def test_failed_job_persists_error_and_resumes_from_checkpoint(database):
    class FlakyOpenAlex:
        attempts = 0

        def fetch_page(self, *, cursor, filters):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("temporary upstream outage")
            assert cursor == "*"
            return {"results": [work()], "meta": {"next_cursor": None}}

    ingestor = OpenAlexIngestor(database, FlakyOpenAlex())
    filters = {"filter": "publication_year:2024"}
    with pytest.raises(RuntimeError, match="temporary upstream outage"):
        ingestor.ingest(filters=filters, limit=1)
    failed_job = database.scalar(select(IngestionJob).where(IngestionJob.run_key == run_key(filters)))
    assert failed_job.status == "failed"
    assert failed_job.last_error == "temporary upstream outage"
    assert failed_job.next_cursor == "*"
    resumed = ingestor.ingest(filters=filters, limit=1)
    assert resumed.status == "complete"
    assert database.scalar(select(func.count()).select_from(Publication)) == 1


def test_rate_limit_retry_after_is_honored_and_key_is_not_logged():
    request_count = 0
    delays = []

    def response(request):
        nonlocal request_count
        request_count += 1
        assert request.headers["Authorization"] == "Bearer fixture-secret"
        assert "api_key" not in request.url.params
        assert request.url.params["cursor"] == "*"
        assert request.url.params["per_page"] == "100"
        assert "mailto:nobody@example.org" in request.headers["User-Agent"]
        if request_count == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"meta": {}, "results": []}, request=request)

    client = OpenAlexClient(
        api_key="fixture-secret",
        mailto="nobody@example.org",
        transport=httpx.MockTransport(response),
        sleep=delays.append,
    )
    try:
        assert client.fetch_page(cursor="*", filters={})["results"] == []
    finally:
        client.close()
    assert request_count == 2 and delays == [0.0]


def test_upsert_is_idempotent_and_preserves_missing_vs_zero(database):
    records = [work(), work("https://openalex.org/W101", cited_by_count=None, abstract=False)]
    upsert_page(database, records)
    upsert_page(database, records)
    database.commit()
    assert database.scalar(select(func.count()).select_from(Publication)) == 2
    zero = database.scalar(
        select(Publication).where(Publication.openalex_id == "https://openalex.org/W100")
    )
    missing = database.scalar(
        select(Publication).where(Publication.openalex_id == "https://openalex.org/W101")
    )
    assert zero.cited_by_count == 0
    assert missing.cited_by_count is None and missing.abstract is None
    assert zero.authors[0]["name"] == "Test Author"
    assert zero.concepts[0]["name"] == "Test concept"
    assert zero.source_metadata["id"] == zero.openalex_id
    assert zero.retrieved_at is not None


def test_malformed_openalex_metadata_is_safe():
    assert normalize_work(None) is None
    assert normalize_work({"id": "https://openalex.org/Wnot-an-id"}) is None
    normalized = normalize_work(
        {
            "id": "https://openalex.org/W1",
            "title": 123,
            "publication_date": "not-a-date",
            "cited_by_count": "0",
            "abstract_inverted_index": [],
        }
    )
    assert normalized["title"] is None
    assert normalized["publication_date"] is None
    assert normalized["cited_by_count"] is None
    assert normalized["abstract"] is None
    assert reconstruct_abstract({"broken": "positions"}) is None


def test_embeddings_batch_cache_retry_and_search(database, monkeypatch):
    upsert_page(database, [work(), work("https://openalex.org/W101")])
    database.commit()

    class Encoder:
        def __init__(self):
            self.calls = 0
            self.fail_once = True

        def embed(self, texts):
            self.calls += 1
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("transient model failure")
            return [np.ones(384, dtype=np.float32) * (1 if "W100" in text else 2) for text in texts]

    # Fixture-backed encoder is deterministic test machinery, never used by the production CLI.
    encoder = Encoder()
    result = generate_embeddings(database, encoder, batch_size=2, sleep=lambda _: None)
    assert result == {"generated": 2, "failed": 0, "skipped_missing_text": 0}
    assert encoder.calls == 2
    assert database.scalar(select(func.count()).select_from(PublicationEmbedding)) == 2
    result = generate_embeddings(database, encoder, batch_size=2, sleep=lambda _: None)
    assert result["generated"] == 0 and encoder.calls == 2
    upsert_page(database, [{"id": "https://openalex.org/W100", "title": "Updated source text"}])
    database.commit()
    refreshed = generate_embeddings(database, encoder, batch_size=2, sleep=lambda _: None)
    assert refreshed["generated"] == 1 and encoder.calls == 3
    hits = search_publications(database, "fixture", "lexical", 10)
    assert hits and hits[0].publication.openalex_id == "https://openalex.org/W101"
    import backend.app.services.search as search_service

    class QueryEncoder:
        def embed(self, texts):
            return [np.ones(384, dtype=np.float32)]

    monkeypatch.setattr(search_service, "FastEmbedEncoder", lambda _: QueryEncoder())
    semantic_hits = search_publications(database, "fixture research", "semantic", 10)
    assert semantic_hits and semantic_hits[0].publication.openalex_id == "https://openalex.org/W100"


def test_missing_embedding_text_is_skipped_then_resumed_when_source_changes(database):
    openalex_id = "https://openalex.org/W102"
    upsert_page(database, [{"id": openalex_id, "title": None, "abstract_inverted_index": None}])
    database.commit()

    class Encoder:
        def embed(self, texts):
            assert texts == ["Title added later"]
            return [np.ones(384, dtype=np.float32)]

    class MustNotRun:
        def embed(self, texts):
            raise AssertionError("records without text must not get fabricated embeddings")

    assert generate_embeddings(database, MustNotRun()) == {
        "generated": 0,
        "failed": 0,
        "skipped_missing_text": 1,
    }
    row = database.scalar(select(PublicationEmbedding))
    assert row.status == "skipped" and row.vector is None
    upsert_page(database, [{"id": openalex_id, "title": "Title added later"}])
    database.commit()
    assert generate_embeddings(database, Encoder()) == {
        "generated": 1,
        "failed": 0,
        "skipped_missing_text": 0,
    }
    row = database.scalar(select(PublicationEmbedding))
    assert row.status == "complete" and len(row.vector) == 384


def test_search_api_returns_actual_persisted_publication_and_method(database):
    upsert_page(database, [work()])
    database.commit()

    def override_db():
        yield database

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            response = test_client.get(
                "/api/v1/search", params={"q": "fixture", "method": "lexical"}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_method"] == "lexical"
    assert payload["results"][0]["openalex_id"] == "https://openalex.org/W100"
    assert payload["results"][0]["cited_by_count"] == 0


def test_postgresql_publication_persistence_and_search_in_ci():
    if get_settings().app_env != "ci":
        pytest.skip("requires the live PostgreSQL integration job")
    openalex_id = "https://openalex.org/W1000001"
    with SessionLocal() as session:
        upsert_page(session, [work(openalex_id)])
        session.commit()
    try:
        with TestClient(app) as test_client:
            response = test_client.get(
                "/api/v1/search", params={"q": "fixture", "method": "lexical"}
            )
        assert response.status_code == 200
        assert any(item["openalex_id"] == openalex_id for item in response.json()["results"])
        with SessionLocal() as session:
            stored = session.scalar(
                select(Publication).where(Publication.openalex_id == openalex_id)
            )
            assert stored is not None and stored.source_metadata["id"] == openalex_id
    finally:
        with SessionLocal() as session:
            session.query(Publication).filter(Publication.openalex_id == openalex_id).delete()
            session.commit()
