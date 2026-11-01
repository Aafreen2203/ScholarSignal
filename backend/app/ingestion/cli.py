import argparse
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.db.session import SessionLocal
from backend.app.ingestion.embeddings import FastEmbedEncoder, generate_embeddings
from backend.app.ingestion.openalex import OpenAlexClient, OpenAlexIngestor, run_key, upsert_page
from backend.app.ingestion.openalex_usage import (
    DEFAULT_DAILY_CEILING_USD,
    USD_PER_CREDIT,
    OpenAlexBudgetGuard,
)
from backend.app.models import IngestionJob


def _filters(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        if ":" not in value:
            raise argparse.ArgumentTypeError(f"filter must use FIELD:VALUE: {value}")
        key, item = value.split(":", 1)
        if not key or not item:
            raise argparse.ArgumentTypeError(f"filter must use FIELD:VALUE: {value}")
        result[key] = item
    return (
        {"filter": ",".join(f"{key}:{result[key]}" for key in sorted(result))}
        if result
        else {}
    )


def main():
    parser = argparse.ArgumentParser(
        description="Ingest OpenAlex works and generate publication embeddings"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    works = subparsers.add_parser("works", help="Fetch works with OpenAlex cursor paging")
    works.add_argument("--filter", action="append", default=[], metavar="FIELD:VALUE")
    works.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum works to store this invocation; default from settings",
    )
    works.add_argument("--per-page", type=int, default=None)
    subparsers.add_parser("budget", help="Check and persist current OpenAlex rate-limit usage")
    smoke = subparsers.add_parser(
        "smoke", help="Fetch and persist one page of at most five works (no pagination)"
    )
    smoke.add_argument("--filter", action="append", default=[], metavar="FIELD:VALUE")
    embeddings = subparsers.add_parser(
        "embeddings", help="Generate missing or stale publication vectors"
    )
    embeddings.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    settings = get_settings()
    with SessionLocal() as session:
        if args.command in {"works", "budget", "smoke"}:
            settings.require_openalex_credentials()
            api_key = settings.openalex_api_key.get_secret_value()
            guard = OpenAlexBudgetGuard()
            filters = _filters(args.filter) if args.command in {"works", "smoke"} else {}
            client = OpenAlexClient(
                api_key=api_key,
                mailto=settings.openalex_mailto,
                base_url=settings.openalex_base_url,
                per_page=5
                if args.command == "smoke"
                else getattr(args, "per_page", None) or settings.openalex_per_page,
                budget_guard=guard,
                budget_session=session,
            )
            try:
                if args.command == "budget":
                    rate_limit = client.fetch_rate_limit()
                    limit = rate_limit.rate_limit
                    used = (limit.limit_credits - limit.remaining_credits) * USD_PER_CREDIT
                    remaining = limit.remaining_credits * USD_PER_CREDIT
                    reset = datetime.now(UTC) + timedelta(seconds=limit.reset_seconds)
                    print(json.dumps({
                        "daily_limit_usd": str(limit.limit_credits * USD_PER_CREDIT),
                        "account_used_usd": str(used),
                        "account_remaining_usd": str(remaining),
                        "request_cost_usd": str(limit.cost_usd),
                        "reset_at_utc": reset.isoformat(),
                        "project_daily_ceiling_usd": str(DEFAULT_DAILY_CEILING_USD),
                        "project_spend_usd": str(guard.usage_for_day(session)),
                    }))
                    return
                if args.command == "works":
                    client.fetch_rate_limit()
                    job = OpenAlexIngestor(session, client).ingest(
                        filters=filters,
                        limit=args.limit
                        if args.limit is not None
                        else settings.openalex_default_limit,
                    )
                else:
                    # This controlled path makes exactly one Works request and never
                    # follows OpenAlex's next_cursor, regardless of response size.
                    page = client.fetch_page_response(cursor="*", filters=filters)
                    if not page.rate_limit.complete:
                        raise RuntimeError(
                            "OpenAlex usage data was incomplete; page was not persisted."
                        )
                    works = page.payload.get("results")
                    if not isinstance(works, list):
                        raise RuntimeError("OpenAlex returned an invalid page envelope.")
                    works = works[:5]
                    upserted = upsert_page(session, works)
                    checkpoint_filters = {**filters, "smoke_page_size": 5}
                    next_cursor = (
                        page.payload.get("meta", {}).get("next_cursor")
                        if isinstance(page.payload.get("meta"), dict)
                        else None
                    )
                    job = session.scalar(
                        select(IngestionJob).where(
                            IngestionJob.run_key == run_key(checkpoint_filters)
                        )
                    )
                    current = datetime.now(UTC)
                    if job is None:
                        job = IngestionJob(
                            run_key=run_key(checkpoint_filters),
                            source="openalex",
                            filters=checkpoint_filters,
                            status="paused" if next_cursor else "complete",
                            next_cursor=next_cursor,
                            pages_processed=1,
                            records_seen=len(works),
                            records_upserted=upserted,
                            started_at=current,
                            finished_at=current,
                            updated_at=current,
                        )
                        session.add(job)
                    else:
                        job.status = "paused" if next_cursor else "complete"
                        job.next_cursor = next_cursor
                        job.page_offset = 0
                        job.pages_processed += 1
                        job.records_seen += len(works)
                        job.records_upserted += upserted
                        job.finished_at = job.updated_at = current
                    session.commit()
            finally:
                client.close()
            print(
                json.dumps(
                    {
                        "job_id": job.id,
                        "status": job.status,
                        "pages": job.pages_processed,
                        "records_seen": job.records_seen,
                        "records_upserted": job.records_upserted,
                        "next_cursor_saved": bool(job.next_cursor),
                        "last_error": job.last_error,
                        "request_count": 1 if args.command == "smoke" else None,
                    }
                )
            )
        else:
            result = generate_embeddings(
                session,
                FastEmbedEncoder(settings.embedding_model_name),
                batch_size=args.batch_size or settings.embedding_batch_size,
                model_name=settings.embedding_model_name,
                model_version=settings.embedding_model_version,
            )
            print(json.dumps(result))


if __name__ == "__main__":
    main()
