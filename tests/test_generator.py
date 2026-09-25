from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from scripts.generate_data import DECOY_MERCHANTS, PLANTED_MERCHANTS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT_ROOT / "scripts" / "generate_data.py"


def directory_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("generator")
    first = root / "first"
    second = root / "second"
    for output_dir in (first, second):
        completed = subprocess.run(
            [sys.executable, str(GENERATOR), "--output-dir", str(output_dir)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Synthetic dataset generated" in completed.stdout
        assert "Planted merchants:" in completed.stdout
    return {"first": first, "second": second}


@pytest.fixture(scope="module")
def connection(generated: dict[str, Path]) -> duckdb.DuckDBPyConnection:
    data_dir = generated["first"]
    connection = duckdb.connect()
    connection.read_csv(str(data_dir / "merchants.csv")).create_view("merchants")
    connection.read_csv(str(data_dir / "transactions.csv")).create_view("transactions")
    connection.read_csv(str(data_dir / "refunds.csv")).create_view("refunds")
    connection.read_csv(str(data_dir / "chargebacks.csv")).create_view("chargebacks")
    yield connection
    connection.close()


def scalar(connection: duckdb.DuckDBPyConnection, sql: str, parameters: list[object] | None = None) -> int:
    result = connection.execute(sql, parameters or []).fetchone()
    assert result is not None
    return int(result[0])


def test_row_counts_are_in_expected_ranges(
    generated: dict[str, Path], connection: duckdb.DuckDBPyConnection
) -> None:
    manifest = json.loads((generated["first"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["as_of_utc"] == "2026-09-24T00:00:00Z"
    assert manifest["seed"] == 20260924
    assert 195 <= scalar(connection, "SELECT count(*) FROM merchants") <= 205
    assert 195_000 <= scalar(connection, "SELECT count(*) FROM transactions") <= 205_000
    assert 2_000 <= scalar(connection, "SELECT count(*) FROM refunds") <= 3_000
    assert 400 <= scalar(connection, "SELECT count(*) FROM chargebacks") <= 500


def test_all_planted_merchants_exist(connection: duckdb.DuckDBPyConnection) -> None:
    rows = connection.execute(
        "SELECT planted_issue, merchant_id FROM merchants WHERE is_planted ORDER BY planted_issue"
    ).fetchall()
    assert dict(rows) == PLANTED_MERCHANTS


def test_chargeback_spike_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    recent, older = connection.execute(
        """
        SELECT
            count(*) FILTER (WHERE occurred_at >= TIMESTAMPTZ '2026-09-17 00:00:00+00'),
            count(*) FILTER (WHERE occurred_at < TIMESTAMPTZ '2026-08-25 00:00:00+00')
        FROM chargebacks
        WHERE merchant_id = 'M0001'
        """
    ).fetchone()
    assert recent >= 50
    assert older == 3


def test_card_testing_burst_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    count, cards, sources = connection.execute(
        """
        SELECT count(*), count(DISTINCT card_token), count(DISTINCT ip_token)
        FROM transactions
        WHERE merchant_id = 'M0002'
          AND amount_cents BETWEEN 100 AND 199
          AND occurred_at >= TIMESTAMPTZ '2026-09-21 21:00:00+00'
          AND occurred_at < TIMESTAMPTZ '2026-09-21 22:00:00+00'
        """
    ).fetchone()
    assert count == 300
    assert cards == 300
    assert sources == 1


def test_refund_abuse_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    assert scalar(connection, "SELECT count(*) FROM refunds WHERE merchant_id = 'M0003'") == 250


def test_below_review_limit_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    assert scalar(
        connection,
        """
        SELECT count(*) FROM transactions
        WHERE merchant_id = 'M0004' AND amount_cents BETWEEN 9900 AND 9999
        """,
    ) >= 400


def test_shared_bank_account_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    rows = connection.execute(
        """
        SELECT merchant_id FROM merchants
        WHERE bank_account_token = (
            SELECT bank_account_token FROM merchants WHERE merchant_id = 'M0005'
        )
        ORDER BY merchant_id
        """
    ).fetchall()
    assert rows == [("M0005",), ("M0100",)]
    oldest, newest = connection.execute(
        """
        SELECT arg_min(merchant_id, created_at), arg_max(merchant_id, created_at)
        FROM merchants WHERE merchant_id IN ('M0005', 'M0100')
        """
    ).fetchone()
    assert oldest == "M0100"
    assert newest == "M0005"


def test_dormant_merchant_suddenly_active_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    old_count, gap_count, recent_count = connection.execute(
        """
        SELECT
            count(*) FILTER (WHERE occurred_at < TIMESTAMPTZ '2026-05-27 00:00:00+00'),
            count(*) FILTER (
                WHERE occurred_at >= TIMESTAMPTZ '2026-06-26 00:00:00+00'
                  AND occurred_at < TIMESTAMPTZ '2026-08-25 00:00:00+00'
            ),
            count(*) FILTER (WHERE occurred_at >= TIMESTAMPTZ '2026-09-21 00:00:00+00')
        FROM transactions WHERE merchant_id = 'M0006'
        """
    ).fetchone()
    assert old_count >= 690
    assert gap_count == 0
    assert recent_count == 300


def test_volume_above_declared_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    volume, declared = connection.execute(
        """
        SELECT sum(t.amount_cents), max(m.declared_monthly_volume_cents)
        FROM transactions t JOIN merchants m USING (merchant_id)
        WHERE t.merchant_id = 'M0007'
          AND t.status = 'approved'
          AND t.occurred_at >= TIMESTAMPTZ '2026-08-25 00:00:00+00'
        """
    ).fetchone()
    assert volume > declared * 20


def test_ticket_size_jump_is_planted(connection: duckdb.DuckDBPyConnection) -> None:
    historical_average, recent_average = connection.execute(
        """
        SELECT
            avg(amount_cents) FILTER (WHERE occurred_at < TIMESTAMPTZ '2026-09-17 00:00:00+00'),
            avg(amount_cents) FILTER (WHERE occurred_at >= TIMESTAMPTZ '2026-09-17 00:00:00+00')
        FROM transactions WHERE merchant_id = 'M0008' AND status = 'approved'
        """
    ).fetchone()
    assert recent_average > historical_average * 6


def test_all_decoy_merchants_exist(connection: duckdb.DuckDBPyConnection) -> None:
    rows = connection.execute(
        "SELECT decoy_scenario, merchant_id FROM merchants WHERE is_decoy ORDER BY decoy_scenario"
    ).fetchall()
    assert dict(rows) == DECOY_MERCHANTS


def test_two_runs_are_byte_identical(generated: dict[str, Path]) -> None:
    first_hashes = directory_hashes(generated["first"])
    second_hashes = directory_hashes(generated["second"])
    assert first_hashes == second_hashes
    assert set(first_hashes) == {
        "chargebacks.csv",
        "manifest.json",
        "merchants.csv",
        "refunds.csv",
        "transactions.csv",
    }
