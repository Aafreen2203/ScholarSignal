# Current limitations

- The available corpus is five OpenAlex records. It is enough to verify the
  ingestion/search paths and product flows, not broad research coverage.
- Retrieval evaluation is a five-query, five-document, single-annotator pilot.
  Its metrics and warm local latencies are recorded in `EVALUATION.md` but do
  not establish general quality or production performance.
- Hybrid retrieval is bounded to 1,000 candidates per method. The API indicates
  a capped result set; larger corpora need careful retrieval/pagination tuning.
- Author/topic filtering currently searches serialized JSON metadata with
  `ILIKE`, which is functional but not index-backed. At larger corpus sizes,
  normalize/index those fields or use PostgreSQL JSON/full-text indexes and
  benchmark filter combinations before production use.
- OpenAlex ingestion and embedding generation are operator-run CLI tasks. No
  background worker or scheduled ingestion is enabled. This is intentional for
  budget safety and must not be treated as an unattended pipeline.
- The local $0.10-per-UTC-day OpenAlex project ceiling and persistent ledger are
  implemented, but they do not replace account-level dashboard monitoring.
  The previous ingestion smoke request cost $0.0001. Do not resume its cursor
  without deliberate approval and a fresh verified budget state.
- Authentication uses a signed cookie token. Logout clears the browser cookie
  but there is no server-side token revocation/rotation. Rate limits key by
  normalized-email digest and do not include a trusted client-IP limit.
- There is no production deployment or load test. Compose startup, schema
  migrations, local persistence, API, and browser flows are verified only in
  the local Docker environment. Hosted GitHub Actions has not been observed.
- Automated backend tests emit a Starlette/httpx TestClient deprecation
  warning; tests still pass. The dependency combination should be upgraded
  deliberately with CI coverage.
- Google Fonts are fetched from the network by the UI; system fallback fonts
  are used offline.
- No learned ranking, graph ML, personalization, external LLM, or scheduled
  ingestion has been introduced.
