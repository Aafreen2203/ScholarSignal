from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete

from backend.app.db.session import SessionLocal, get_db
from backend.app.main import app
from backend.app.models import Publication


def _insert_publication(client) -> Publication:
    override = app.dependency_overrides.get(get_db)
    if override is None:
        session = SessionLocal()
        close = session.close
    else:
        generator = override()
        session = next(generator)

        def close():
            generator.close()
    try:
        publication = Publication(
            openalex_id="https://openalex.org/W9999999999",
            title="A study of protein structure prediction",
            abstract="We evaluate protein structure methods and biomolecular interactions.",
            authors=[{"name": "A. Researcher"}],
            publication_date=date(2024, 4, 1),
            doi="https://doi.org/10.1234/example",
            concepts=[{"display_name": "Protein structure"}],
            topics=[{"display_name": "Biology"}],
            cited_by_count=3,
            source="openalex",
            source_metadata={
                "primary_location": {"source": {"display_name": "Example Journal"}},
                "referenced_works": ["https://openalex.org/W123456"],
            },
            retrieved_at=datetime.now(UTC),
        )
        session.add(publication)
        session.commit()
        session.refresh(publication)
        return publication
    finally:
        close()


def _register(client, email: str):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a sufficiently long passphrase", "display_name": "Reader"},
    )
    assert response.status_code == 201


@pytest.fixture
def publication(client):
    record = _insert_publication(client)
    yield record
    override = app.dependency_overrides.get(get_db)
    if override is None:
        session = SessionLocal()
        close = session.close
    else:
        generator = override()
        session = next(generator)

        def close():
            generator.close()

    try:
        session.execute(delete(Publication).where(Publication.id == record.id))
        session.commit()
    finally:
        close()


def test_private_workspace_search_detail_and_history(client, publication):
    _register(client, "workspace-owner@example.com")

    search = client.get("/api/v1/search", params={"q": "protein structure", "method": "lexical"})
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["results_capped"] is False
    assert search.json()["results"][0]["openalex_id"] == publication.openalex_id
    assert search.json()["results"][0]["title"] == publication.title
    history = client.get("/api/v1/search/history")
    assert history.status_code == 200
    assert history.json()[0]["query"] == "protein structure"

    detail = client.get(f"/api/v1/publications/{publication.id}")
    assert detail.status_code == 200
    assert detail.json()["venue"] == "Example Journal"
    assert detail.json()["references"] == ["https://openalex.org/W123456"]
    assert client.get("/api/v1/workspace/recent").json()[0]["id"] == publication.id

    assert client.post("/api/v1/workspace/saved", json={"publication_id": publication.id}).status_code == 204
    assert client.post("/api/v1/workspace/saved", json={"publication_id": publication.id}).status_code == 204
    assert len(client.get("/api/v1/workspace/saved").json()) == 1
    collection_response = client.post(
        "/api/v1/workspace/collections", json={"name": "Protein reading", "description": "Review set"}
    )
    assert collection_response.status_code == 201
    collection_id = collection_response.json()["id"]
    assert client.post(
        f"/api/v1/workspace/collections/{collection_id}/publications",
        json={"publication_id": publication.id},
    ).status_code == 204
    assert [p["id"] for p in client.get(f"/api/v1/workspace/collections/{collection_id}/publications").json()] == [publication.id]
    note_response = client.post(
        "/api/v1/workspace/notes",
        json={"title": "Follow up", "body": "Compare methods.", "publication_id": publication.id},
    )
    assert note_response.status_code == 201
    note_id = note_response.json()["id"]
    assert client.patch(f"/api/v1/workspace/notes/{note_id}", json={"body": "Compare method limitations."}).status_code == 200

    client.post("/api/v1/auth/logout")
    _register(client, "workspace-other@example.com")
    assert client.get("/api/v1/workspace/saved").json() == []
    assert client.get("/api/v1/workspace/notes").json() == []
    assert client.get("/api/v1/workspace/collections").json() == []
    assert client.get(f"/api/v1/workspace/collections/{collection_id}/publications").status_code == 404
    assert client.patch(f"/api/v1/workspace/notes/{note_id}", json={"title": "Tamper"}).status_code == 404


def test_search_history_retention_is_bounded_and_ordered(client, monkeypatch):
    from backend.app.api import search as search_api

    monkeypatch.setattr(search_api, "SEARCH_HISTORY_RETENTION", 2)
    _register(client, "history-owner@example.com")
    for query in ("history 1", "history 2", "history 3"):
        assert client.get("/api/v1/search", params={"q": query, "method": "lexical"}).status_code == 200
    history = client.get("/api/v1/search/history")
    assert [item["query"] for item in history.json()] == ["history 3", "history 2"]
