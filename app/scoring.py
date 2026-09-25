"""Explainable weighted scoring for the merchant watchlist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.database import DEFAULT_DATABASE_PATH
from app.query_library import QUERY_NAMES, load_query, run_query


DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parent / "scoring_weights.json"
SEVERITY_WEIGHTS = {"High": 30, "Medium": 20, "Low": 10}
INFORMATIONAL_QUERIES = {"portfolio_summary", "volume_concentration"}


def load_weights(weights_path: Path = DEFAULT_WEIGHTS_PATH) -> dict[str, int]:
    """Load and validate the complete query-to-weight mapping."""
    raw_weights = json.loads(weights_path.read_text(encoding="utf-8"))
    if not isinstance(raw_weights, dict):
        raise ValueError("Scoring weights must be a JSON object")

    weights = {str(query_name): int(weight) for query_name, weight in raw_weights.items()}
    if set(weights) != set(QUERY_NAMES):
        missing = sorted(set(QUERY_NAMES) - set(weights))
        extra = sorted(set(weights) - set(QUERY_NAMES))
        raise ValueError(f"Scoring config mismatch; missing={missing}, extra={extra}")

    for query_name, weight in weights.items():
        severity = load_query(query_name)["severity"]
        expected_weight = 0 if query_name in INFORMATIONAL_QUERIES else SEVERITY_WEIGHTS[severity]
        if weight != expected_weight:
            raise ValueError(
                f"Weight for {query_name} is {weight}; expected {expected_weight} for {severity}"
            )
    return weights


def build_watchlist(
    database_path: Path = DEFAULT_DATABASE_PATH,
    weights_path: Path = DEFAULT_WEIGHTS_PATH,
) -> list[dict[str, Any]]:
    """Run weighted flag queries and return a deterministic ranked watchlist."""
    weights = load_weights(weights_path)
    merchants: dict[str, dict[str, Any]] = {}

    for query_name in QUERY_NAMES:
        weight = weights[query_name]
        if weight <= 0:
            continue

        query_metadata = load_query(query_name)
        query_result = run_query(query_name, database_path=database_path)
        reasons_by_merchant: dict[str, list[str]] = {}
        merchant_names: dict[str, str] = {}

        for row in query_result["rows"]:
            merchant_id = str(row["merchant_id"])
            merchant_names[merchant_id] = str(row["merchant_name"])
            reason = str(row["reason"])
            reasons = reasons_by_merchant.setdefault(merchant_id, [])
            if reason not in reasons:
                reasons.append(reason)

        for merchant_id, reasons in reasons_by_merchant.items():
            merchant = merchants.setdefault(
                merchant_id,
                {
                    "merchant_id": merchant_id,
                    "merchant_name": merchant_names[merchant_id],
                    "score": 0,
                    "reason_chips": [],
                    "triggered_queries": [],
                },
            )
            merchant["score"] += weight
            merchant["reason_chips"].append(query_metadata["title"])
            merchant["triggered_queries"].append(
                {
                    "name": query_name,
                    "title": query_metadata["title"],
                    "severity": query_metadata["severity"],
                    "weight": weight,
                    "reason": " | ".join(reasons),
                }
            )

    ranked_merchants = sorted(
        merchants.values(),
        key=lambda merchant: (-merchant["score"], merchant["merchant_id"]),
    )
    for rank, merchant in enumerate(ranked_merchants, start=1):
        merchant["rank"] = rank
        merchant["triggered_queries"].sort(
            key=lambda query: (-query["weight"], query["title"])
        )
        merchant["reason_chips"] = [
            query["title"] for query in merchant["triggered_queries"]
        ]
    return ranked_merchants


def build_score_distribution(
    database_path: Path = DEFAULT_DATABASE_PATH,
    weights_path: Path = DEFAULT_WEIGHTS_PATH,
) -> list[dict[str, int | str]]:
    """Return the ranked fields required by the inline score chart."""
    return [
        {
            "rank": merchant["rank"],
            "merchant_id": merchant["merchant_id"],
            "score": merchant["score"],
        }
        for merchant in build_watchlist(
            database_path=database_path,
            weights_path=weights_path,
        )
    ]
