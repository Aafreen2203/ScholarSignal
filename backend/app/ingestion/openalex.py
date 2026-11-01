import hashlib
import json
import logging
import random
import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.ingestion.text import embedding_text, embedding_text_hash
from backend.app.models import IngestionJob, Publication

logger = logging.getLogger(__name__)
OPENALEX_BASE_URL = "https://api.openalex.org"
DEFAULT_PER_PAGE = 100
MAX_RETRIES = 5


class OpenAlexError(RuntimeError):
    pass


def _retry_delay(attempt: int, retry_after: str | None, *, now: datetime | None = None) -> float:
    if retry_after:
        try:
            return max(0.0, min(300.0, float(retry_after)))
        except ValueError:
            try:
                when = parsedate_to_datetime(retry_after)
                return max(0.0, min(300.0, (when - (now or datetime.now(UTC))).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(60.0, 2.0**attempt) + random.uniform(0, min(1.0, 2.0**attempt * 0.1))


class OpenAlexClient:
    def __init__(
        self,
        *,
        api_key: str,
        mailto: str,
        base_url: str = OPENALEX_BASE_URL,
        per_page: int = DEFAULT_PER_PAGE,
        timeout: float = 30.0,
        max_retries: int = MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not api_key.strip():
            raise ValueError(
                "OPENALEX_API_KEY is required; cursor paging past page one needs a key"
            )
        if not mailto.strip() or "@" not in mailto:
            raise ValueError("OPENALEX_MAILTO must be a contact email for the OpenAlex polite pool")
        if not 1 <= per_page <= DEFAULT_PER_PAGE:
            raise ValueError("OpenAlex per_page must be between 1 and 100")
        self.api_key = api_key
        self.mailto = mailto
        self.per_page = per_page
        self.max_retries = max_retries
        self.sleep = sleep
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "User-Agent": f"ScholarSignal/0.1 (mailto:{mailto})",
                "Authorization": f"Bearer {api_key}",
            },
        )

    def fetch_page(self, *, cursor: str, filters: dict[str, Any]) -> dict[str, Any]:
        params = {**filters, "per_page": self.per_page, "cursor": cursor}
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get("/works", params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries:
                        self.sleep(_retry_delay(attempt, response.headers.get("Retry-After")))
                        continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                    raise OpenAlexError("OpenAlex returned an invalid page envelope")
                return payload
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self.max_retries:
                    raise OpenAlexError(
                        f"OpenAlex request failed after retries ({type(exc).__name__})"
                    ) from exc
                self.sleep(_retry_delay(attempt, None))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # Avoid echoing the request URL because it contains the API key.
                raise OpenAlexError(f"OpenAlex returned HTTP {status}") from None
        raise OpenAlexError("OpenAlex retries exhausted")

    def close(self):
        self.client.close()


def reconstruct_abstract(inverted_index: Any) -> str | None:
    if not isinstance(inverted_index, dict):
        return None
    positions: dict[int, str] = {}
    try:
        for word, offsets in inverted_index.items():
            if not isinstance(word, str) or not isinstance(offsets, list):
                continue
            for offset in offsets:
                if isinstance(offset, int) and offset >= 0:
                    positions[offset] = word
        if not positions:
            return None
        # Reject pathological sparse arrays rather than allocating an unbounded gap.
        if max(positions) > 100_000:
            return None
        return " ".join(positions[index] for index in sorted(positions)) or None
    except (TypeError, ValueError):
        return None


def _items(values: Any, *, key: str, name: str) -> list[dict[str, Any]] | None:
    if not isinstance(values, list):
        return None
    result = []
    for item in values:
        if not isinstance(item, dict):
            continue
        item_id, label = item.get(key), item.get(name)
        if isinstance(item_id, dict):
            item_id = item_id.get("id")
        if isinstance(label, dict):
            label = label.get("display_name")
        if isinstance(item_id, str) or isinstance(label, str):
            result.append(
                {
                    "id": item_id.strip() or None if isinstance(item_id, str) else None,
                    "name": label.strip() or None if isinstance(label, str) else None,
                    "score": item.get("score")
                    if isinstance(item.get("score"), (int, float))
                    else None,
                }
            )
    return result


def normalize_work(work: Any, retrieved_at: datetime | None = None) -> dict[str, Any] | None:
    if not isinstance(work, dict):
        return None
    openalex_id = work.get("id")
    if not isinstance(openalex_id, str) or not re.fullmatch(
        r"https://openalex\.org/W[0-9]+", openalex_id
    ):
        return None
    raw_date = work.get("publication_date")
    try:
        publication_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else None
    except ValueError:
        publication_date = None
    cited = work.get("cited_by_count")
    cited_by_count = (
        cited if isinstance(cited, int) and not isinstance(cited, bool) and cited >= 0 else None
    )
    doi = work.get("doi")
    if isinstance(doi, str):
        doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/") or None
    else:
        doi = None
    authorships = work.get("authorships")
    authors = None
    if isinstance(authorships, list):
        authors = []
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            if isinstance(author, dict):
                name = author.get("display_name") if isinstance(author.get("display_name"), str) else None
                authors.append(
                    {
                        "id": author.get("id") if isinstance(author.get("id"), str) else None,
                        "name": name.strip() or None if name else None,
                        "orcid": author.get("orcid")
                        if isinstance(author.get("orcid"), str)
                        else None,
                    }
                )
    title_value = work.get("title") if isinstance(work.get("title"), str) else None
    title = title_value.strip() or None if title_value else None
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    return {
        "openalex_id": openalex_id,
        "title": title,
        "abstract": abstract,
        "embedding_text_hash": embedding_text_hash(embedding_text(title, abstract)),
        "authors": authors,
        "publication_date": publication_date,
        "doi": doi,
        "concepts": _items(work.get("concepts"), key="id", name="display_name"),
        "topics": _items(work.get("topics"), key="id", name="display_name"),
        "cited_by_count": cited_by_count,
        "source": "openalex",
        "source_metadata": work,
        "retrieved_at": retrieved_at or datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


def run_key(filters: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(filters, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def upsert_page(session: Session, results: list[Any], retrieved_at: datetime | None = None) -> int:
    normalized = [record for work in results if (record := normalize_work(work, retrieved_at))]
    if not normalized:
        return 0
    dialect = session.bind.dialect.name if session.bind else ""
    if dialect == "postgresql":
        statement = pg_insert(Publication).values(normalized)
        statement = statement.on_conflict_do_update(
            index_elements=[Publication.openalex_id],
            set_={
                key: getattr(statement.excluded, key)
                for key in normalized[0]
                if key != "openalex_id"
            },
        )
        session.execute(statement)
        return len(normalized)
    # Portable test/dev fallback. The production ingestion path remains PostgreSQL-backed.
    count = 0
    for values in normalized:
        publication = session.scalar(
            select(Publication).where(Publication.openalex_id == values["openalex_id"])
        )
        if publication is None:
            publication = Publication(**values)
            session.add(publication)
        else:
            for key, value in values.items():
                if key != "openalex_id":
                    setattr(publication, key, value)
        count += 1
    session.flush()
    return count


class OpenAlexIngestor:
    def __init__(self, session: Session, client: OpenAlexClient):
        self.session, self.client = session, client

    def ingest(
        self, *, filters: dict[str, Any], limit: int | None = None, resume: bool = True
    ) -> IngestionJob:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        key = run_key(filters)
        job = (
            self.session.scalar(select(IngestionJob).where(IngestionJob.run_key == key))
            if resume
            else None
        )
        if job is None:
            job = IngestionJob(
                run_key=key, source="openalex", filters=filters, status="pending", next_cursor="*"
            )
            self.session.add(job)
            self.session.flush()
        if job.status == "complete":
            # A completed run is a safe refresh point; source IDs make the rescan idempotent.
            job.status = "pending"
            job.next_cursor = "*"
            job.page_offset = 0
            job.pages_processed = job.records_seen = job.records_upserted = 0
            job.started_at = job.finished_at = None
        job.status, job.last_error = "running", None
        job.started_at = job.started_at or datetime.now(UTC)
        self.session.commit()
        remaining = limit
        try:
            while True:
                page_cursor = job.next_cursor or "*"
                page = self.client.fetch_page(cursor=page_cursor, filters=filters)
                page_results = page["results"]
                page_start = job.page_offset
                available = page_results[page_start:]
                results = available if remaining is None else available[:remaining]
                stamp = datetime.now(UTC)
                upserted = upsert_page(self.session, results, stamp)
                page_fully_processed = page_start + len(results) >= len(page_results)
                if page_fully_processed:
                    job.pages_processed += 1
                job.records_seen += len(results)
                job.records_upserted += upserted
                next_cursor = (
                    page.get("meta", {}).get("next_cursor")
                    if isinstance(page.get("meta"), dict)
                    else None
                )
                # A limited page is stored with the same cursor; the unique source ID makes refetch idempotent.
                if remaining is not None:
                    remaining -= len(results)
                exhausted = page_fully_processed and (
                    not isinstance(next_cursor, str) or not next_cursor or not page_results
                )
                reached_limit = remaining is not None and remaining <= 0 and not exhausted
                if page_fully_processed:
                    job.next_cursor = next_cursor if isinstance(next_cursor, str) else None
                    job.page_offset = 0
                else:
                    # OpenAlex cursors advance by page, so retain the cursor plus record offset.
                    job.next_cursor = page_cursor
                    job.page_offset = page_start + len(results)
                job.status = "paused" if reached_limit else "complete" if exhausted else "running"
                job.finished_at = (
                    datetime.now(UTC) if job.status in {"paused", "complete"} else None
                )
                job.updated_at = datetime.now(UTC)
                self.session.commit()
                if job.status != "running":
                    return job
        except Exception as exc:
            self.session.rollback()
            job = self.session.get(IngestionJob, job.id)
            job.status = "failed"
            job.last_error = str(exc)[:2000]
            job.updated_at = datetime.now(UTC)
            self.session.commit()
            raise
