from __future__ import annotations

from pathlib import Path

import pytest

from app.database import DEFAULT_DATA_DIR, initialize_database
from app.query_library import (
    ALLOWED_CATEGORIES,
    ALLOWED_SEVERITIES,
    QUERY_DIR,
    QUERY_NAMES,
    REQUIRED_HEADER_FIELDS,
    load_query,
    parse_header,
    run_query,
)


@pytest.fixture(scope="module")
def query_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database_path = tmp_path_factory.mktemp("queries") / "portfolio.duckdb"
    initialize_database(database_path=database_path, data_dir=DEFAULT_DATA_DIR)
    return database_path


@pytest.mark.parametrize(
    ("query_name", "expected_merchant"),
    [
        ("chargeback_spike", "M0001"),
        ("card_testing_burst", "M0002"),
        ("refund_abuse", "M0003"),
        ("below_review_limit", "M0004"),
        ("shared_bank_account", "M0005"),
        ("dormant_suddenly_active", "M0006"),
        ("volume_above_declared", "M0007"),
        ("ticket_size_jump", "M0008"),
    ],
)
def test_query_returns_only_its_planted_merchant(
    query_database: Path, query_name: str, expected_merchant: str
) -> None:
    result = run_query(query_name, database_path=query_database)
    returned_merchants = {row["merchant_id"] for row in result["rows"]}
    assert returned_merchants == {expected_merchant}
    assert result["row_count"] == 1


def test_every_query_file_has_standard_header() -> None:
    query_files = sorted(QUERY_DIR.glob("*.sql"))
    assert {path.stem for path in query_files} == set(QUERY_NAMES)
    for query_file in query_files:
        metadata = parse_header(query_file.read_text(encoding="utf-8"))
        missing = [field for field in REQUIRED_HEADER_FIELDS if not metadata.get(field)]
        assert not missing, f"{query_file.name} missing: {', '.join(missing)}"
        severity, separator, reason = metadata["severity"].partition("|")
        assert severity.strip() in ALLOWED_SEVERITIES
        assert separator and reason.strip()
        assert metadata["category"] in ALLOWED_CATEGORIES
        assert "illustrative" in metadata["thresholds"].lower()
        assert "utc" in metadata["data_notes"].lower()
        assert "synthetic" in metadata["data_notes"].lower()
        assert "reason" in metadata["output_columns"].lower()


@pytest.mark.parametrize(
    ("query_name", "decoy_merchant"),
    [
        ("refund_abuse", "M0199"),
        ("dormant_suddenly_active", "M0198"),
        ("volume_above_declared", "M0198"),
        ("ticket_size_jump", "M0200"),
    ],
)
def test_similar_decoy_is_excluded_as_documented(
    query_database: Path, query_name: str, decoy_merchant: str
) -> None:
    result = run_query(query_name, database_path=query_database)
    returned_merchants = {row["merchant_id"] for row in result["rows"]}
    assert decoy_merchant not in returned_merchants
    assert decoy_merchant in load_query(query_name)["sql"]


def test_portfolio_summary_returns_every_merchant(query_database: Path) -> None:
    result = run_query("portfolio_summary", database_path=query_database)
    merchant_ids = [row["merchant_id"] for row in result["rows"]]
    assert result["row_count"] == 200
    assert len(set(merchant_ids)) == 200
    assert {"M0198", "M0199", "M0200"}.issubset(merchant_ids)


def test_decline_rate_outliers_returns_bounded_ranked_list(query_database: Path) -> None:
    result = run_query("decline_rate_outliers", database_path=query_database)
    assert 1 <= result["row_count"] <= 20
    assert [row["portfolio_rank"] for row in result["rows"]] == list(
        range(1, result["row_count"] + 1)
    )
    assert all(row["decline_rate"] >= 0.20 for row in result["rows"])


def test_shared_attributes_includes_planted_bank_cluster(query_database: Path) -> None:
    result = run_query("shared_merchant_attributes", database_path=query_database)
    linkages = {
        (row["merchant_id"], row["linked_merchant_id"], row["shared_attribute"])
        for row in result["rows"]
    }
    assert ("M0005", "M0100", "bank_account") in linkages
    assert ("M0100", "M0005", "bank_account") in linkages


def test_volume_concentration_returns_top_ten_in_order(query_database: Path) -> None:
    result = run_query("volume_concentration", database_path=query_database)
    assert result["row_count"] == 10
    assert [row["portfolio_rank"] for row in result["rows"]] == list(range(1, 11))
    shares = [row["portfolio_volume_share"] for row in result["rows"]]
    assert shares == sorted(shares, reverse=True)
    assert "M0007" in {row["merchant_id"] for row in result["rows"]}
