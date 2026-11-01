import argparse
import json
import logging

from backend.app.core.config import get_settings
from backend.app.db.session import SessionLocal
from backend.app.ingestion.embeddings import FastEmbedEncoder, generate_embeddings
from backend.app.ingestion.openalex import OpenAlexClient, OpenAlexIngestor


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
        if args.command == "works":
            api_key = settings.openalex_api_key.get_secret_value()
            client = OpenAlexClient(
                api_key=api_key,
                mailto=settings.openalex_mailto,
                base_url=settings.openalex_base_url,
                per_page=args.per_page or settings.openalex_per_page,
            )
            try:
                job = OpenAlexIngestor(session, client).ingest(
                    filters=_filters(args.filter),
                    limit=args.limit if args.limit is not None else settings.openalex_default_limit,
                )
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
