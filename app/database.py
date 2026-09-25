"""DuckDB setup and connection helpers for the generated portfolio data."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = DEFAULT_DATA_DIR / "merchant_portfolio.duckdb"

TABLE_FILES = {
    "merchants": "merchants.csv",
    "transactions": "transactions.csv",
    "refunds": "refunds.csv",
    "chargebacks": "chargebacks.csv",
}


def get_read_write_connection(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> duckdb.DuckDBPyConnection:
    """Return a connection allowed to create and update database objects."""
    resolved_path = database_path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(resolved_path), read_only=False)


def get_read_only_connection(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection that rejects database writes."""
    resolved_path = database_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {resolved_path}")
    return duckdb.connect(str(resolved_path), read_only=True)


def get_restricted_read_only_connection(
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> duckdb.DuckDBPyConnection:
    """Return a read-only connection with file and extension access disabled."""
    resolved_path = database_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"DuckDB database not found: {resolved_path}")
    return duckdb.connect(
        str(resolved_path),
        read_only=True,
        config={
            "enable_external_access": "false",
            "threads": "1",
            "memory_limit": "256MB",
        },
    )


def expected_row_counts(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, int]:
    """Read the generator's expected table counts from its manifest."""
    manifest_path = data_dir.resolve() / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Generator manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = manifest.get("row_counts")
    if not isinstance(counts, dict):
        raise ValueError("Generator manifest does not contain row_counts")
    return {table: int(counts[table]) for table in TABLE_FILES}


def table_row_counts(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Return the current row count for each generated-data table."""
    counts: dict[str, int] = {}
    for table_name in TABLE_FILES:
        result = connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()
        if result is None:
            raise RuntimeError(f"Could not count rows in {table_name}")
        counts[table_name] = int(result[0])
    return counts


def initialize_database(
    database_path: Path = DEFAULT_DATABASE_PATH,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> dict[str, int]:
    """Replace the four DuckDB tables with the generator's current CSV output."""
    resolved_data_dir = data_dir.resolve()
    expected = expected_row_counts(resolved_data_dir)
    source_paths = {
        table_name: resolved_data_dir / filename
        for table_name, filename in TABLE_FILES.items()
    }
    missing = [str(path) for path in source_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Generated data file(s) not found: " + ", ".join(missing))

    connection = get_read_write_connection(database_path)
    try:
        connection.execute("BEGIN TRANSACTION")
        for table_name, source_path in source_paths.items():
            connection.execute(f"DROP TABLE IF EXISTS {table_name}")
            connection.read_csv(str(source_path), header=True).create(table_name)
        actual = table_row_counts(connection)
        if actual != expected:
            raise ValueError(f"Loaded row counts {actual} do not match manifest {expected}")
        connection.execute("COMMIT")
        return actual
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
