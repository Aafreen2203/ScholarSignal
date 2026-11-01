# ML methodology

Milestone 2 adds semantic retrieval with FastEmbed 0.9.1 and the
`sentence-transformers/all-MiniLM-L6-v2` model (384 dimensions). The model is
used as published; ScholarSignal does not fine-tune it. Embeddings are generated
from each publication's available title and abstract, with a SHA-256 content
hash for cache invalidation. Rows retain model name/version, dimensions,
generation status, attempts, and timestamps. Missing source text is marked
`skipped`; no vector is fabricated.

The lexical baseline is PostgreSQL English full-text ranking. Semantic
retrieval compares a real query embedding with persisted vectors using cosine
similarity in pgvector. Hybrid retrieval uses reciprocal-rank fusion with a
bounded candidate window. Search explains each method and reports when hybrid
candidates were capped. Related-paper results use stored publication vectors.

The repository includes a five-query, five-document, single-annotator pilot
judgment set and records Precision@3, Recall@3, MRR, nDCG@3, and warm local
latency. It is explicitly a tiny functional pilot, not a representative
benchmark; see [EVALUATION.md](EVALUATION.md). The system does not fine-tune the
encoder, call an external LLM, or use evaluation data for model training.
Graph ML, personalization, and learned/advanced ranking remain out of scope.

