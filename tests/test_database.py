from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from app.database import (
    get_read_only_connection,
    get_read_write_connection,
    initialize_database,
    table_row_counts,
)
from scripts.generate_data import generate_dataset


@pytest.fixture(scope="module")
def loaded_database(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("database")
    data_dir = root / "generated"
    database_path = root / "portfolio.duckdb"
    generate_dataset(data_dir)
    initialize_database(database_path=database_path, data_dir=data_dir)
    return {"data_dir": data_dir, "database_path": database_path}


def test_database_loads_without_error(loaded_database: dict[str, Path]) -> None:
    database_path = loaded_database["database_path"]
    assert database_path.is_file()
    connection = get_read_write_connection(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert tables == {"merchants", "transactions", "refunds", "chargebacks"}


def test_table_counts_match_generator_output(loaded_database: dict[str, Path]) -> None:
    manifest = json.loads(
        (loaded_database["data_dir"] / "manifest.json").read_text(encoding="utf-8")
    )
    connection = get_read_only_connection(loaded_database["database_path"])
    try:
        assert table_row_counts(connection) == manifest["row_counts"]
    finally:
        connection.close()


@pytest.mark.parametrize(
    "write_statement",
    [
        "INSERT INTO merchants SELECT * FROM merchants LIMIT 1",
        "CREATE TABLE forbidden_write(value INTEGER)",
    ],
)
def test_read_only_connection_rejects_writes(
    loaded_database: dict[str, Path], write_statement: str
) -> None:
    connection = get_read_only_connection(loaded_database["database_path"])
    try:
        with pytest.raises(duckdb.Error, match="read-only"):
            connection.execute(write_statement)
    finally:
        connection.close()
