# Data pipeline

## OpenAlex works

The ingestion CLI requests real records from `https://api.openalex.org/works`.
Configure `OPENALEX_API_KEY` and a real contact address in `OPENALEX_MAILTO`;
the key is required to continue cursor paging past the first page. OpenAlex
currently documents `per_page` up to 100. The client sends the key in the
request, identifies ScholarSignal with the contact address, retries network,
server, and 429 responses, honors `Retry-After`, and never logs request URLs
that contain credentials. See the [OpenAlex authentication and rate-limit
docs](https://help.openalex.org/api/authentication/) and [cursor paging
docs](https://help.openalex.org/api/paging/).

Example small smoke run (requires configured credentials and internet access):

```sh
docker compose exec backend python -m backend.app.ingestion.cli works \
  --filter publication_year:2024 --limit 5
```

`OPENALEX_DEFAULT_LIMIT` defaults to 25; set `--limit` explicitly for each
run. `OPENALEX_PER_PAGE` defaults to 100. Ingestion checkpoints store the
normalized filter, cursor, within-page offset, status, timestamps, counters,
and last error. A limited run pauses and can resume with the same filters.
Rerunning a completed filter starts a fresh cursor scan. Each page's
publication upserts and checkpoint advance commit together. OpenAlex work IDs
are unique, so rescans update provenance and metadata without duplicate rows.

The publication keeps normalized fields and the original OpenAlex response in
`source_metadata`; `retrieved_at` records local retrieval time. Abstract
inverted indexes are reconstructed defensively. Unavailable dates, abstracts,
citation counts, and other fields remain `NULL`; an explicit citation count of
zero remains `0`. `concepts` and current `topics` are both preserved when
provided.

The smoke command has not been run against OpenAlex in this environment because
no API key/contact address is configured. Deterministic records in automated
tests are test fixtures only and are not presented as real source data.

## Embeddings

`python -m backend.app.ingestion.cli embeddings` processes publications in
bounded batches. It uses the real FastEmbed implementation of
`sentence-transformers/all-MiniLM-L6-v2` (FastEmbed 0.9.1; 384 dimensions;
Apache-2.0 model license). See the [FastEmbed model registry](https://qdrant.tech/documentation/embeddings/fastembed/)
and [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
The container's `embedding_cache` volume retains downloaded model artifacts.
Each embedding row stores the model name/version, dimensions, source-content
hash, status, retry count, failure text, vector, and generation timestamp.
Publications keep the normalized title/abstract hash too, so the worker selects
only missing or stale rows and failed work in bounded joined batches instead of
scanning every publication or issuing one embedding lookup per row. Unchanged
complete rows are reused; changed content is regenerated. A
process restart reclaims pending/generating/failed rows on the next invocation.
Missing title and abstract are recorded as skipped instead of receiving a
fabricated vector.

## Search

Lexical search uses PostgreSQL English full-text query parsing and `ts_rank_cd`
over title and abstract, backed by a GIN index. Semantic search embeds the
query with the same configured model and asks pgvector for nearest cosine
neighbors through an HNSW index. Search returns publication records, a score,
the selected retrieval method, and a short explanation. It does not expose
latency or quality metrics until a valid labelled evaluation set is available.
SQLite fallback behavior exists only to keep deterministic unit tests portable;
Compose and CI integration runs use PostgreSQL/pgvector.

## Data and evaluation boundaries

Automated fixtures use synthetic IDs and explicit fixture titles. They exist to
test parsing, persistence, pagination, retries, caching, and API behavior; no
fixture is counted as ingested OpenAlex data. We do not have a labelled query,
relevance-judgment dataset yet, so no latency or retrieval quality metric is
reported. No fixture is used as an evaluation query set.
