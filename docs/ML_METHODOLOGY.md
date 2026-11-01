# ML methodology

Milestone 2 adds semantic retrieval with FastEmbed 0.9.1 and the
`sentence-transformers/all-MiniLM-L6-v2` model (384 dimensions). The model is
used as published; ScholarSignal does not fine-tune it. Embeddings are generated
from each publication's available title and abstract, with a SHA-256 content
hash for cache invalidation. Rows retain model name/version, dimensions,
generation status, attempts, and timestamps. Missing source text is marked
`skipped`; no vector is fabricated.

The first retrieval baseline is PostgreSQL English full-text ranking. Semantic
retrieval compares a real query embedding with persisted vectors using cosine
similarity in pgvector. Search explains the selected method. There is no labelled
evaluation dataset yet, so latency and relevance metrics are withheld. Training,
graph ML, personalization, and advanced ranking remain out of scope.

