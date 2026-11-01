from datetime import UTC, datetime
from decimal import Decimal

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
from backend.app.ingestion.openalex_usage import (
    DEFAULT_DAILY_CEILING_USD,
    OpenAlexBudgetError,
    OpenAlexBudgetGuard,
    OpenAlexRateLimit,
)
from backend.app.main import app
from backend.app.models import (
    IngestionJob,
    OpenAlexDailyUsage,
    OpenAlexUsageEvent,
    Publication,
    PublicationEmbedding,
)
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
        assert "fixture-secret" not in repr(client)
        assert "fixture-secret" not in repr(client.client.auth)
        assert "fixture-secret" not in repr(client.client.headers)
        assert client.fetch_page(cursor="*", filters={})["results"] == []
    finally:
        client.close()
    assert request_count == 2 and delays == [0.0]


def test_openalex_response_preserves_rate_limit_headers_with_payload():
    def response(request):
        return httpx.Response(
            200,
            headers={
                "X-RateLimit-Limit": "10000",
                "X-RateLimit-Remaining": "8766",
                "X-RateLimit-Credits-Used": "1",
                "X-RateLimit-Reset": "43200",
            },
            json={"meta": {"cost_usd": 0.0001}, "results": []},
            request=request,
        )

    client = OpenAlexClient(
        api_key="fixture-secret",
        mailto="researcher@example.test",
        transport=httpx.MockTransport(response),
    )
    try:
        result = client.fetch_page_response(cursor="*", filters={})
    finally:
        client.close()

    assert result.payload["results"] == []
    assert result.headers["x-ratelimit-limit"] == "10000"
    assert result.headers["x-ratelimit-reset"] == "43200"
    assert result.rate_limit.limit_credits == 10000
    assert result.rate_limit.remaining_credits == 8766
    assert result.rate_limit.credits_used == 1
    assert result.rate_limit.cost_usd == Decimal("0.0001")


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {
            "X-RateLimit-Limit": "not-a-number",
            "X-RateLimit-Remaining": "-1",
            "X-RateLimit-Credits-Used": "NaN",
            "X-RateLimit-Reset": "tomorrow",
        },
    ],
)
def test_malformed_or_missing_rate_headers_remain_unknown(headers):
    parsed = OpenAlexRateLimit.from_response(headers)
    assert parsed.limit_credits is None
    assert parsed.remaining_credits is None
    assert parsed.credits_used is None
    assert parsed.reset_seconds is None
    assert parsed.cost_usd is None
    assert parsed.complete is False


def test_current_usage_json_schema_is_supported_without_confusing_daily_and_request_usage():
    fixed_now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    parsed = OpenAlexRateLimit.from_response(
        {},
        {
            "daily_budget_usd": 1.0,
            "daily_used_usd": 0.2,
            "daily_remaining_usd": 0.8,
            "resets_at": "2026-11-02T00:00:00Z",
            "prepaid_balance_usd": 5.0,
            "prepaid_remaining_usd": 4.0,
            "meta": {"cost": 0.0001},
        },
        now=fixed_now,
    )
    assert parsed.limit_credits == Decimal("10000")
    assert parsed.remaining_credits == Decimal("8000.0")
    assert parsed.credits_used == Decimal("1")
    assert parsed.cost_usd == Decimal("0.0001")
    assert parsed.reset_seconds == 43200
    assert parsed.complete


def test_legacy_usage_json_schema_and_case_insensitive_headers():
    fixed_now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    parsed = OpenAlexRateLimit.from_response(
        {
            "x-ratelimit-limit": "10000",
            "X-RATELIMIT-REMAINING": "9000",
            "x-ratelimit-credits-used": "1",
            "X-RateLimit-Reset": "3600",
        },
        {"meta": {"cost_usd": 0.0001}},
        now=fixed_now,
    )
    assert parsed.limit_credits == Decimal("10000")
    assert parsed.remaining_credits == Decimal("9000")
    assert parsed.credits_used == 1
    assert parsed.cost_usd == Decimal("0.0001")
    assert parsed.reset_seconds == 3600
    assert parsed.complete

    body_only = OpenAlexRateLimit.from_response(
        {},
        {
            "meta": {
                "daily_budget_usd": 1.0,
                "daily_used_usd": 0.1,
                "daily_remaining_usd": 0.9,
                "resets_at": "2026-11-01T13:00:00Z",
                "cost_usd": 0.0002,
            }
        },
        now=fixed_now,
    )
    assert body_only.limit_credits == Decimal("10000")
    assert body_only.remaining_credits == Decimal("9000.0")
    assert body_only.credits_used == Decimal("2")
    assert body_only.reset_seconds == 3600
    assert body_only.complete


def test_missing_and_conflicting_budget_values_fail_closed():
    missing = OpenAlexRateLimit.from_response(
        {},
        {
            "daily_budget_usd": 1.0,
            "daily_used_usd": 0.2,
            "daily_remaining_usd": 0.8,
            "resets_at": "2026-11-02T00:00:00Z",
        },
        now=datetime(2026, 11, 1, 12, tzinfo=UTC),
    )
    assert missing.limit_credits == 10000
    assert missing.remaining_credits == 8000
    assert missing.credits_used is None and missing.cost_usd is None
    assert missing.reset_seconds == 43200 and not missing.complete

    conflicting = OpenAlexRateLimit.from_response(
        {"X-RateLimit-Limit": "10000", "X-RateLimit-Remaining": "7000"},
        {
            "daily_budget_usd": 1.0,
            "daily_used_usd": 0.2,
            "daily_remaining_usd": 0.8,
            "resets_at": "2026-11-02T00:00:00Z",
            "meta": {"cost_usd": 0.0001},
        },
        now=datetime(2026, 11, 1, 12, tzinfo=UTC),
    )
    assert conflicting.remaining_credits is None
    assert conflicting.complete is False


def test_rate_limit_endpoint_accepts_bearer_auth_and_parses_usage_body_without_leaking_key():
    secret = "fixture-secret-never-print"

    def response(request):
        assert request.url.path == "/rate-limit"
        assert request.headers["Authorization"] == f"Bearer {secret}"
        assert "api_key" not in request.url.params
        return httpx.Response(
            200,
            headers={"X-RateLimit-Credits-Used": "1"},
            json={
                "daily_budget_usd": 1.0,
                "daily_used_usd": 0.2,
                "daily_remaining_usd": 0.8,
                "resets_at": "2026-11-02T00:00:00Z",
                "meta": {"cost_usd": 0.0001},
            },
            request=request,
        )

    client = OpenAlexClient(
        api_key=secret,
        mailto="researcher@example.test",
        transport=httpx.MockTransport(response),
    )
    try:
        result = client.fetch_rate_limit()
        assert result.rate_limit.complete
        assert secret not in repr(client)
        assert secret not in repr(result)
    finally:
        client.close()


def _rate_headers(*, limit="10000", remaining="9900", used="1", reset="3600"):
    return OpenAlexRateLimit.from_response(
        {
            "X-RateLimit-Limit": limit,
            "X-RateLimit-Remaining": remaining,
            "X-RateLimit-Credits-Used": used,
            "X-RateLimit-Reset": reset,
        }
    )


def test_budget_guard_persists_project_usage_across_sessions(database):
    guard = OpenAlexBudgetGuard()
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    reservation = guard.reserve(
        database, Decimal("0.0001"), now=now, allow_initial_budget_check=True
    )
    guard.record_response(database, reservation, _rate_headers(), now=now)
    assert guard.usage_for_day(database, now=now) == Decimal("0.0001")

    sessions = sessionmaker(bind=database.get_bind(), expire_on_commit=False)
    with sessions() as reopened_session:
        assert guard.usage_for_day(reopened_session, now=now) == Decimal("0.0001")
        next_request = guard.reserve(reopened_session, Decimal("0.0001"), now=now)
        assert next_request.amount_usd == Decimal("0.0001")


def test_budget_check_reserves_headroom_and_records_nonzero_response_cost(database):
    guard = OpenAlexBudgetGuard()
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    reservation = guard.reserve_budget_check(database, now=now)
    assert reservation.amount_usd == DEFAULT_DAILY_CEILING_USD
    guard.record_response(database, reservation, _rate_headers(), now=now)
    assert guard.usage_for_day(database, now=now) == Decimal("0.0001")
    next_check = guard.reserve_budget_check(database, now=now)
    assert next_check.amount_usd == DEFAULT_DAILY_CEILING_USD - Decimal("0.0001")


def test_budget_guard_refuses_when_account_or_project_ceiling_is_exhausted(database):
    guard = OpenAlexBudgetGuard()
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    reservation = guard.reserve(
        database, DEFAULT_DAILY_CEILING_USD, now=now, allow_initial_budget_check=True
    )
    costly_response = OpenAlexRateLimit.from_response(
        {
            "X-RateLimit-Limit": "10000",
            "X-RateLimit-Remaining": "9900",
            "X-RateLimit-Credits-Used": "1000",
            "X-RateLimit-Reset": "3600",
        },
        {"meta": {"cost_usd": 0.1}},
    )
    guard.record_response(database, reservation, costly_response, now=now)
    with pytest.raises(OpenAlexBudgetError, match="project spending ceiling"):
        guard.reserve(database, Decimal("0.0001"), now=now)


def test_budget_guard_refuses_when_external_account_usage_exceeds_ceiling(database):
    guard = OpenAlexBudgetGuard()
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    reservation = guard.reserve(
        database, Decimal("0.0001"), now=now, allow_initial_budget_check=True
    )
    guard.record_response(
        database,
        reservation,
        _rate_headers(remaining="8900"),
        now=now,
    )
    with pytest.raises(OpenAlexBudgetError, match="daily usage exceeds"):
        guard.reserve(database, Decimal("0.0001"), now=now)


def test_budget_guard_fails_closed_on_unknown_snapshot_and_resets_by_utc_day(database):
    guard = OpenAlexBudgetGuard()
    local_time = datetime.fromisoformat("2026-11-02T00:30:00+02:00")
    utc_time = local_time.astimezone(UTC)
    assert utc_time.date().isoformat() == "2026-11-01"
    reservation = guard.reserve(
        database, Decimal("0.0001"), now=local_time, allow_initial_budget_check=True
    )
    incomplete = OpenAlexRateLimit.from_response({"X-RateLimit-Limit": "10000"})
    guard.record_response(database, reservation, incomplete, now=local_time)
    with pytest.raises(OpenAlexBudgetError, match="unverified"):
        guard.reserve(database, Decimal("0.0001"), now=utc_time)

    next_day = datetime(2026, 11, 2, 0, 1, tzinfo=UTC)
    assert guard.usage_for_day(database, now=next_day) == Decimal("0")
    bootstrap = guard.reserve(
        database, Decimal("0.0001"), now=next_day, allow_initial_budget_check=True
    )
    assert bootstrap.utc_date == next_day.date()


def test_manual_dashboard_reconciliation_preserves_history_and_allows_bounded_request(database):
    now = datetime(2026, 11, 1, 12, tzinfo=UTC)
    row = OpenAlexDailyUsage(
        utc_date=now.date(),
        project_spend_usd=Decimal("0.10"),
        reserved_usd=Decimal("0"),
        request_count=1,
        budget_verified=False,
    )
    database.add(row)
    database.add(
        OpenAlexUsageEvent(
            utc_date=now.date(),
            event_type="legacy_aggregate",
            amount_usd=Decimal("0.10"),
            actual_cost_known=False,
            details={"request_level_costs": "unknown"},
        )
    )
    database.commit()

    guard = OpenAlexBudgetGuard()
    guard.record_manual_reconciliation(
        database,
        daily_budget_usd=Decimal("1.00"),
        daily_used_usd=Decimal("0.00"),
        daily_remaining_usd=Decimal("1.00"),
        reset_at=datetime(2026, 11, 2, 0, tzinfo=UTC),
        evidence="User-reported official dashboard reading",
        now=now,
    )
    refreshed = database.get(OpenAlexDailyUsage, now.date())
    assert refreshed.project_spend_usd == Decimal("0.00")
    assert refreshed.request_count == 1
    assert refreshed.daily_limit_credits == Decimal("10000")
    assert refreshed.remaining_credits == Decimal("10000")
    assert refreshed.last_credits_used is None
    assert refreshed.budget_verified
    events = list(database.scalars(select(OpenAlexUsageEvent).order_by(OpenAlexUsageEvent.id)))
    assert events[0].event_type == "legacy_aggregate"
    assert events[0].actual_cost_known is False
    assert events[1].event_type == "manual_reconciliation"
    assert events[1].amount_usd == Decimal("-0.10")
    assert events[1].details["prior_request_cost"] == "unknown"

    reservation = guard.reserve(database, Decimal("0.0001"), now=now)
    assert reservation.amount_usd == Decimal("0.0001")
    assert refreshed.reserved_usd == Decimal("0.0001")


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


def test_hybrid_search_filters_paginates_and_semantic_sort_is_global(database, monkeypatch):
    upsert_page(
        database,
        [
            {"id": "https://openalex.org/W200", "title": "protein structure methods", "publication_date": "2020-01-01", "cited_by_count": 4},
            {"id": "https://openalex.org/W201", "title": "protein structure evaluation", "publication_date": "2024-01-01", "cited_by_count": 12},
        ],
    )
    database.commit()
    publications = list(database.scalars(select(Publication).order_by(Publication.id)))
    for publication in publications:
        database.add(
            PublicationEmbedding(
                publication_id=publication.id,
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_version="fastembed-0.9.1",
                dimensions=384,
                content_hash=publication.embedding_text_hash or "fixture-hash",
                status="complete",
                vector=np.ones(384, dtype=np.float32).tolist(),
            )
        )
    database.commit()

    import backend.app.services.search as search_service

    class QueryEncoder:
        def embed(self, texts):
            assert len(texts) == 1
            return [np.ones(384, dtype=np.float32)]

    monkeypatch.setattr(search_service, "FastEmbedEncoder", lambda _: QueryEncoder())
    from backend.app.services.search import search_publications_page

    semantic = search_publications_page(
        database, "protein", "semantic", limit=1, offset=0, sort_by="date"
    )
    assert semantic.total == 2
    assert semantic.hits[0].publication.openalex_id == "https://openalex.org/W201"
    hybrid = search_publications_page(
        database,
        "protein",
        "hybrid",
        limit=1,
        filters={"year_from": 2024},
    )
    assert hybrid.total == 1
    assert hybrid.capped is False
    assert hybrid.hits[0].publication.openalex_id == "https://openalex.org/W201"
    assert "Hybrid RRF" in hybrid.hits[0].explanation

    def override_db():
        yield database

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            related = test_client.get(f"/api/v1/publications/{publications[0].id}/related")
    finally:
        app.dependency_overrides.clear()
    assert related.status_code == 200
    assert related.json()["retrieval_method"] == "semantic_similarity"
    assert related.json()["results"][0]["openalex_id"] == "https://openalex.org/W201"


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
