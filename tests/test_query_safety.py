from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "INSERT INTO merchants SELECT * FROM merchants LIMIT 1",
        "UPDATE merchants SET merchant_name = 'changed'",
        "DELETE FROM merchants",
        "CREATE TABLE forbidden(value INTEGER)",
        "DROP TABLE merchants",
        "ATTACH 'other.duckdb' AS other",
        "COPY merchants TO 'merchants.csv'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "PRAGMA version",
    ],
)
def test_rejects_non_select_or_multiple_statements(client: TestClient, sql: str) -> None:
    response = client.post("/api/custom-query", json={"sql": sql})
    assert response.status_code == 400
    assert response.json()["detail"] in {
        "Exactly one SQL statement is allowed.",
        "Only a single SELECT or WITH statement is allowed.",
    }


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv_auto('data/merchants.csv')",
        "SELECT * FROM read_parquet('data/example.parquet')",
        "SELECT * FROM read_json_auto('data/manifest.json')",
        "SELECT * FROM glob('data/*')",
    ],
)
def test_rejects_external_file_access(client: TestClient, sql: str) -> None:
    response = client.post("/api/custom-query", json={"sql": sql})
    assert response.status_code == 400
    assert response.json() == {"detail": "External file access is disabled."}


def test_normal_select_and_with_statements_work(client: TestClient) -> None:
    response = client.post(
        "/api/custom-query",
        json={
            "sql": """
                WITH selected AS (
                    SELECT merchant_id, merchant_name
                    FROM merchants
                    WHERE merchant_id IN ('M0001', 'M0002')
                )
                SELECT * FROM selected ORDER BY merchant_id
            """,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["columns"] == ["merchant_id", "merchant_name"]
    assert [row["merchant_id"] for row in payload["rows"]] == ["M0001", "M0002"]
    assert payload["truncated"] is False


def test_exact_simple_merchant_select_works(client: TestClient) -> None:
    response = client.post(
        "/api/custom-query",
        json={"sql": "SELECT * FROM merchants LIMIT 5"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 5
    assert [row["merchant_id"] for row in payload["rows"]] == [
        "M0001",
        "M0002",
        "M0003",
        "M0004",
        "M0005",
    ]
    assert payload["rows"][0]["created_at"].endswith("Z")


def test_results_are_capped_at_500_rows(client: TestClient) -> None:
    response = client.post(
        "/api/custom-query",
        json={"sql": "SELECT range AS row_number FROM range(1000)"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 500
    assert payload["row_limit"] == 500
    assert payload["truncated"] is True


def test_expensive_query_is_stopped_by_timeout(client: TestClient) -> None:
    started_at = time.monotonic()
    response = client.post(
        "/api/custom-query",
        json={
            "sql": "SELECT sum(sin(value::DOUBLE)) FROM range(10000000000) AS values(value)"
        },
    )
    elapsed = time.monotonic() - started_at
    assert response.status_code == 408
    assert "execution limit" in response.json()["detail"]
    assert elapsed < 5.0
