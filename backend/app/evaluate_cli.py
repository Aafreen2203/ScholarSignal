"""Run the versioned pilot retrieval evaluation against the configured database."""

import json
from pathlib import Path

from backend.app.db.session import SessionLocal
from backend.app.evaluation import evaluate, load_evaluation
from backend.app.ingestion.embeddings import FastEmbedEncoder


def main():
    dataset_path = Path(__file__).resolve().parents[2] / "evaluation" / "relevance_v1.json"
    dataset = load_evaluation(dataset_path)
    # Warm the existing local model before recording per-query latency.
    next(iter(FastEmbedEncoder().embed(["evaluation model warmup"])))
    with SessionLocal() as session:
        print(json.dumps(evaluate(session, dataset), indent=2))


if __name__ == "__main__":
    main()
