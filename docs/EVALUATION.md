# Retrieval evaluation

## Pilot design

`evaluation/relevance_v1.json` is a versioned convenience set containing five
queries and relevance judgments over all five genuine OpenAlex records already
stored in the local PostgreSQL corpus. The project author made one pass over
the stored titles and abstracts, assigning grade 2 to the directly relevant
paper and grade 0 to the other four. There is no independent adjudication,
partial-grade judgment, query sampling, training split, or test split. The
identifiers refer to the real source records; no synthetic fixtures are used.

This is suitable for a functional pilot only. Five hand-written queries and
five conveniently available records are far too small and subjective to
support a general search-quality claim or model comparison.

## Metrics and run

The evaluation script reports macro-averaged Precision@3, Recall@3, MRR, and
nDCG@3, plus per-query warm-cache mean/median latency. Latency includes local
query embedding for semantic and hybrid search and the database retrieval; it
is a single local Docker run over five records, not a load or production
benchmark. The FastEmbed model was warmed before timing.

Run it against the configured local PostgreSQL database (the Compose model
cache volume is used for local inference):

```bash
docker compose exec backend python -m backend.app.evaluate_cli
```

Observed run on 2026-11-01, using the five stored real OpenAlex records and the
`sentence-transformers/all-MiniLM-L6-v2` local model:

| Method | P@3 | Recall@3 | MRR | nDCG@3 | Mean latency | Median latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Lexical | 0.2000 | 0.6000 | 0.6000 | 0.6000 | 10.853 ms | 3.942 ms |
| Semantic | 0.3333 | 1.0000 | 1.0000 | 1.0000 | 21.385 ms | 12.031 ms |
| Hybrid RRF | 0.3333 | 1.0000 | 1.0000 | 1.0000 | 19.346 ms | 18.305 ms |

These pilot values are not evidence that semantic or hybrid search is generally
better. Two lexical queries returned no result; every query had exactly one
positive judgment; with only five papers and one annotator, a top-ranked
positive is expected to produce deceptively perfect values. Latencies varied
per query, and five-row timing says nothing about production scale. Preserve
these outputs as a baseline smoke record, not as a release-quality metric.

## Next valid evaluation step

Before claiming ranking improvements, expand to a diverse, independently
reviewed query/document judgment set with a documented sampling protocol,
multiple relevance grades, adjudication, and a held-out evaluation split.
Report per-query distributions and confidence intervals in addition to macro
means. Benchmark latency at realistic corpus sizes with warm and cold model
starts separated. Do not use this pilot to tune weights and then treat it as an
unseen test set.
