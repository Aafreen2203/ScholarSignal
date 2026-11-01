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

For a strictly one-page smoke test (at most five works, no pagination):

```sh
docker compose exec -T backend python -m backend.app.ingestion.cli smoke \
  --filter publication_year:2024
```

Observed on 2026-11-01: one `/works` request returned five records and all five
were persisted in PostgreSQL. The response usage values were 10,000 credits
daily limit, 9,999 remaining, 1 credit used ($0.0001), with reset at midnight
UTC. Account usage was $0.0001 and remaining budget was $0.9999. Project spend
was $0.0001, within the $0.10 UTC daily ceiling. The ingestion job remains
paused at its saved next cursor; no additional OpenAlex request was made.

The five persisted records were:

- `W2029648951` — *8 Decolonizing Methodologies: Research and Indigenous Peoples*
- `W3118608800` — *Learning Multiple Layers of Features from Tiny Images*
- `W4392145873` — *Two new Later Stone Age sites from the Final Pleistocene in the Falémé Valley, eastern Senegal*
- `W4393935425` — *Global cancer statistics 2022: GLOBOCAN estimates of incidence and mortality worldwide for 36 cancers in 185 countries*
- `W4396721167` — *Accurate structure prediction of biomolecular interactions with AlphaFold 3*

The persistent usage ledger records request reservations/results and a
separate manual reconciliation event. The prior request's exact cost remains
unknown; the user-reported dashboard reading is recorded as evidence, and the
original $0.10 conservative aggregate remains in the event history.

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

Automated tests use deterministic fixtures only; those fixtures are not
presented as real source data. The smoke run above is separately identified as
real OpenAlex data.

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

After the five-record real-data smoke test, the embedding CLI generated five
vectors and no failures or skips. PostgreSQL verification confirmed that each
of the IDs above has a `complete` row for model
`sentence-transformers/all-MiniLM-L6-v2`, version `fastembed-0.9.1`, dimensions
384, and a finite vector. At that time those were the only publication rows;
no existing valid embedding was regenerated. No external embedding API was
used.

## Search and paper details

Lexical search uses PostgreSQL English full-text query parsing and `ts_rank_cd`
over title and abstract, backed by a GIN index. Semantic search embeds the
query with the same configured model and asks pgvector for nearest cosine
neighbors through an HNSW index. Search returns publication records, a score,
the selected retrieval method, and a short explanation. Latency and ranking
metrics are reported only for the explicitly limited five-query pilot in
`EVALUATION.md`; its single-annotator convenience judgments do not support
general quality claims.
SQLite fallback behavior exists only to keep deterministic unit tests portable;
Compose and CI integration runs use PostgreSQL/pgvector.

The search API supports lexical, semantic, and RRF hybrid methods; year, author,
and topic filters; sorting by relevance/date/citation count; and bounded
pagination. Responses include method and per-result explanations. Hybrid
retrieval is capped at 1,000 candidates per method and reports
`results_capped=true` when the corpus exceeds that candidate window. Semantic
sorts by date or citations order the full filtered vector corpus before
pagination. The portable SQLite implementation is only a deterministic test
fallback; Compose and CI use PostgreSQL/pgvector.

Paper details include only fields present in source data, source provenance,
DOI/OpenAlex links, and up to 50 reference IDs supplied by the source record.
Related-in-library results compare the stored local vectors; they do not make
another OpenAlex request or call an external model API.

Functional checks against the five real records returned the Global Cancer
Statistics paper for `cancer incidence mortality`, AlphaFold 3 for semantic
`protein structure interactions`, and *Decolonizing Methodologies* for hybrid
`Indigenous research methods`. A 2024 filter returned the stored cancer paper.
Next.js proxy browser tests verified paper detail and related records against
the same PostgreSQL rows.

## Data and evaluation boundaries

Automated fixtures use synthetic IDs and explicit fixture titles. They exist to
test parsing, persistence, pagination, retries, caching, and API behavior; no
fixture is counted as ingested OpenAlex data. We do not have a labelled query,
relevance-judgment dataset representative of the wider corpus. A separate
versioned five-record single-annotator pilot exists for smoke evaluation; see
[`EVALUATION.md`](EVALUATION.md) for its labels, measured metrics, and strict
limits. No fixture is used as an evaluation query set.
