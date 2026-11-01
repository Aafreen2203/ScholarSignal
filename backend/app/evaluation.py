"""Small, explicit retrieval evaluation helpers for the labelled pilot set."""

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.services.search import search_publications_page


def retrieval_metrics(ranked_ids: list[str], judgments: dict[str, int], *, k: int = 3):
    if k < 1:
        raise ValueError("k must be positive")
    relevant = {doc_id for doc_id, grade in judgments.items() if grade > 0}
    top_k = ranked_ids[:k]
    relevant_top_k = [doc_id for doc_id in top_k if judgments.get(doc_id, 0) > 0]
    precision = len(relevant_top_k) / k
    recall = len(relevant_top_k) / len(relevant) if relevant else 0.0
    reciprocal_rank = next(
        (1.0 / rank for rank, doc_id in enumerate(ranked_ids, start=1) if doc_id in relevant),
        0.0,
    )

    def dcg(ids: list[str]) -> float:
        return sum((2**judgments.get(doc_id, 0) - 1) / math.log2(rank + 1) for rank, doc_id in enumerate(ids[:k], start=1))

    ideal = sorted(judgments.values(), reverse=True)
    ideal_dcg = sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal[:k], start=1))
    return {
        f"precision@{k}": precision,
        f"recall@{k}": recall,
        "mrr": reciprocal_rank,
        f"ndcg@{k}": dcg(top_k) / ideal_dcg if ideal_dcg else 0.0,
    }


def load_evaluation(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("queries"), list):
        raise ValueError("Unsupported or malformed evaluation dataset")
    return data


def evaluate(session: Session, dataset: dict[str, Any], *, k: int = 3):
    measurements: dict[str, dict[str, list[float]]] = {
        method: {"precision": [], "recall": [], "mrr": [], "ndcg": [], "latency_ms": []}
        for method in ("lexical", "semantic", "hybrid")
    }
    per_query = []
    for item in dataset["queries"]:
        query = item["query"]
        judgments = item["judgments"]
        query_result = {"query_id": item["id"], "query": query, "methods": {}}
        for method in measurements:
            started = time.perf_counter()
            result = search_publications_page(session, query, method, limit=100)
            latency_ms = (time.perf_counter() - started) * 1000
            ids = [hit.publication.openalex_id for hit in result.hits]
            scores = retrieval_metrics(ids, judgments, k=k)
            bucket = measurements[method]
            for metric, score_key in (
                ("precision", f"precision@{k}"),
                ("recall", f"recall@{k}"),
                ("mrr", "mrr"),
                ("ndcg", f"ndcg@{k}"),
            ):
                bucket[metric].append(scores[score_key])
            bucket["latency_ms"].append(latency_ms)
            query_result["methods"][method] = {**scores, "latency_ms": round(latency_ms, 3), "ranked_ids": ids}
        per_query.append(query_result)
    summary = {
        method: {
            **{
                f"{key}@{k}" if key in {"precision", "recall", "ndcg"} else key:
                round(statistics.mean(values), 4) if values else 0.0
                for key, values in metrics.items()
                if key != "latency_ms"
            },
            "mean_latency_ms": round(statistics.mean(metrics["latency_ms"]), 3) if metrics["latency_ms"] else 0.0,
            "median_latency_ms": round(statistics.median(metrics["latency_ms"]), 3) if metrics["latency_ms"] else 0.0,
        }
        for method, metrics in measurements.items()
    }
    return {"dataset": dataset["name"], "k": k, "summary": summary, "queries": per_query}
