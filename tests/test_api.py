from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.query_library import (
    ALLOWED_CATEGORIES,
    ALLOWED_SEVERITIES,
    QUERY_NAMES,
    load_query,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_query_list_returns_every_query_with_display_metadata(client: TestClient) -> None:
    response = client.get("/api/queries")

    assert response.status_code == 200
    queries = response.json()
    assert [query["name"] for query in queries] == list(QUERY_NAMES)

    for query in queries:
        assert query["title"]
        assert query["category"] in ALLOWED_CATEGORIES
        assert query["severity"] in ALLOWED_SEVERITIES


def test_named_query_returns_its_sql_and_results(client: TestClient) -> None:
    response = client.get("/api/queries/chargeback_spike")

    assert response.status_code == 200
    payload = response.json()
    expected_query = load_query("chargeback_spike")
    assert payload["name"] == "chargeback_spike"
    assert payload["sql"] == expected_query["sql"]
    assert payload["columns"][-1] == "reason"
    assert payload["row_count"] == 1
    assert [row["merchant_id"] for row in payload["rows"]] == ["M0001"]


def test_unknown_query_returns_404(client: TestClient) -> None:
    response = client.get("/api/queries/not_a_real_query")

    assert response.status_code == 404
    assert response.json() == {"detail": "Query not found"}


def test_watchlist_endpoint_returns_ranked_explainable_scores(client: TestClient) -> None:
    response = client.get("/api/watchlist")

    assert response.status_code == 200
    watchlist = response.json()
    assert watchlist[0]["merchant_id"] == "M0002"
    assert watchlist[0]["rank"] == 1
    assert watchlist[0]["score"] == 50
    assert watchlist[0]["reason_chips"] == [
        "Card-Testing Velocity Burst",
        "Elevated Decline-Rate Outliers",
    ]
    assert all(query["reason"] for query in watchlist[0]["triggered_queries"])


def test_watchlist_chart_endpoint_matches_watchlist_scores(client: TestClient) -> None:
    watchlist = client.get("/api/watchlist").json()
    response = client.get("/api/watchlist/chart")

    assert response.status_code == 200
    assert response.json() == [
        {
            "rank": merchant["rank"],
            "merchant_id": merchant["merchant_id"],
            "score": merchant["score"],
        }
        for merchant in watchlist
    ]
