from __future__ import annotations

from pathlib import Path

import pytest

from app.database import DEFAULT_DATA_DIR, initialize_database
from app.query_library import QUERY_NAMES
from app.scoring import build_score_distribution, build_watchlist, load_weights
from scripts.generate_data import DECOY_MERCHANTS, PLANTED_MERCHANTS


EXPECTED_CONTRIBUTIONS = {
    "M0001": {"chargeback_spike"},
    "M0002": {"card_testing_burst", "decline_rate_outliers"},
    "M0003": {"refund_abuse"},
    "M0004": {"below_review_limit"},
    "M0005": {"shared_bank_account", "shared_merchant_attributes"},
    "M0006": {"dormant_suddenly_active"},
    "M0007": {"volume_above_declared"},
    "M0008": {"ticket_size_jump"},
    "M0100": {"shared_merchant_attributes"},
}

EXPECTED_SCORES = {
    "M0001": 30,
    "M0002": 50,
    "M0003": 30,
    "M0004": 20,
    "M0005": 40,
    "M0006": 30,
    "M0007": 30,
    "M0008": 20,
    "M0100": 20,
}


@pytest.fixture(scope="module")
def scoring_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database_path = tmp_path_factory.mktemp("scoring") / "portfolio.duckdb"
    initialize_database(database_path=database_path, data_dir=DEFAULT_DATA_DIR)
    return database_path


@pytest.fixture(scope="module")
def watchlist(scoring_database: Path) -> list[dict[str, object]]:
    return build_watchlist(database_path=scoring_database)


def test_config_maps_every_query_to_a_weight() -> None:
    weights = load_weights()
    assert set(weights) == set(QUERY_NAMES)
    assert weights["portfolio_summary"] == 0
    assert weights["volume_concentration"] == 0


@pytest.mark.parametrize("merchant_id", EXPECTED_CONTRIBUTIONS)
def test_expected_merchants_have_exact_query_contributions(
    watchlist: list[dict[str, object]], merchant_id: str
) -> None:
    merchant = next(item for item in watchlist if item["merchant_id"] == merchant_id)
    triggered_query_names = {
        query["name"] for query in merchant["triggered_queries"]
    }
    assert triggered_query_names == EXPECTED_CONTRIBUTIONS[merchant_id]
    assert merchant["score"] == EXPECTED_SCORES[merchant_id]
    assert len(merchant["reason_chips"]) == len(triggered_query_names)
    assert all(query["reason"] for query in merchant["triggered_queries"])


def test_watchlist_contains_only_planted_and_linked_merchants(
    watchlist: list[dict[str, object]],
) -> None:
    watchlist_ids = {merchant["merchant_id"] for merchant in watchlist}
    expected_ids = set(PLANTED_MERCHANTS.values()) | {"M0100"}
    decoy_ids = set(DECOY_MERCHANTS.values())
    clean_ids = {
        f"M{merchant_number:04d}"
        for merchant_number in range(1, 201)
    } - expected_ids - decoy_ids

    assert watchlist_ids == expected_ids
    assert decoy_ids.isdisjoint(watchlist_ids)
    assert clean_ids.isdisjoint(watchlist_ids)
    assert len(watchlist) == 9


def test_watchlist_is_ranked_by_score_then_merchant_id(
    watchlist: list[dict[str, object]],
) -> None:
    expected_order = sorted(
        watchlist,
        key=lambda merchant: (-merchant["score"], merchant["merchant_id"]),
    )
    assert watchlist == expected_order
    assert [merchant["rank"] for merchant in watchlist] == list(
        range(1, len(watchlist) + 1)
    )


def test_chart_data_matches_watchlist_scores(
    scoring_database: Path, watchlist: list[dict[str, object]]
) -> None:
    chart_data = build_score_distribution(database_path=scoring_database)
    assert chart_data == [
        {
            "rank": merchant["rank"],
            "merchant_id": merchant["merchant_id"],
            "score": merchant["score"],
        }
        for merchant in watchlist
    ]
