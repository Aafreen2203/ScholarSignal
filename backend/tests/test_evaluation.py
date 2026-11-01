from math import log2

import pytest

from backend.app.evaluation import load_evaluation, retrieval_metrics


def test_retrieval_metrics_known_ranking():
    judgments = {"relevant-first": 2, "relevant-third": 1, "irrelevant": 0}
    metrics = retrieval_metrics(["relevant-first", "irrelevant", "relevant-third"], judgments, k=3)
    assert metrics["precision@3"] == pytest.approx(2 / 3)
    assert metrics["recall@3"] == pytest.approx(1)
    assert metrics["mrr"] == pytest.approx(1)
    assert metrics["ndcg@3"] == pytest.approx(3.5 / (3 + 1 / log2(3)))


def test_pilot_dataset_is_versioned_and_uses_existing_openalex_ids():
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "evaluation" / "relevance_v1.json"
    dataset = load_evaluation(path)
    assert dataset["schema_version"] == 1
    assert len(dataset["queries"]) == 5
    assert all(len(item["judgments"]) == 5 for item in dataset["queries"])
