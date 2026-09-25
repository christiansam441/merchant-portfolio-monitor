"""Restricted custom SQL validation and isolated execution."""

from __future__ import annotations

import multiprocessing
import json
import re
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import duckdb

from app.database import DEFAULT_DATABASE_PATH, get_restricted_read_only_connection


ROW_LIMIT = 500
EXECUTION_TIMEOUT_SECONDS = 2.5
MAX_SQL_LENGTH = 20_000
ALLOWED_ROOT_KEYWORDS = {"SELECT", "WITH"}


class QueryRejectedError(ValueError):
    """The submitted SQL is outside the permitted read-only grammar."""


class QueryExecutionError(RuntimeError):
    """The submitted SQL failed inside the restricted database connection."""


class QueryTimeoutError(TimeoutError):
    """The submitted SQL exceeded the execution deadline."""


def _leading_keyword(sql: str) -> str:
    """Return the first lexical keyword after leading whitespace and SQL comments."""
    position = 0
    length = len(sql)
    while position < length:
        while position < length and sql[position].isspace():
            position += 1
        if sql.startswith("--", position):
            newline = sql.find("\n", position + 2)
            position = length if newline == -1 else newline + 1
            continue
        if sql.startswith("/*", position):
            comment_end = sql.find("*/", position + 2)
            if comment_end == -1:
                return ""
            position = comment_end + 2
            continue
        break
    match = re.match(r"[A-Za-z_]+", sql[position:])
    return match.group(0).upper() if match else ""


def validate_sql(sql: str) -> str:
    """Use DuckDB's parser plus a root-keyword check to allow one SELECT or WITH."""
    if not sql.strip():
        raise QueryRejectedError("Enter a SELECT or WITH statement.")
    if len(sql) > MAX_SQL_LENGTH:
        raise QueryRejectedError("Query is too long.")

    parser = duckdb.connect()
    try:
        try:
            statements = parser.extract_statements(sql)
        except duckdb.Error as error:
            raise QueryRejectedError("SQL could not be parsed as a valid statement.") from error
    finally:
        parser.close()

    if len(statements) != 1:
        raise QueryRejectedError("Exactly one SQL statement is allowed.")

    statement = statements[0]
    # DuckDB normalizes some commands, including PRAGMA, into a SELECT internally.
    # The original root token prevents those rewrites from entering the allowlist.
    root_keyword = _leading_keyword(sql)
    if statement.type != duckdb.StatementType.SELECT or root_keyword not in ALLOWED_ROOT_KEYWORDS:
        raise QueryRejectedError("Only a single SELECT or WITH statement is allowed.")
    validated_sql = statement.query.strip()
    if validated_sql.endswith(";"):
        validated_sql = validated_sql[:-1].rstrip()
    return validated_sql


def _query_worker(
    database_path: str,
    sql: str,
    row_limit: int,
    result_pipe: Connection,
) -> None:
    """Execute in a disposable process so the parent can enforce a hard deadline."""
    connection = None
    try:
        connection = get_restricted_read_only_connection(Path(database_path))
        relation = connection.sql(sql)
        columns = relation.columns
        column_types = relation.types
        projection = []
        for column, column_type in zip(columns, column_types, strict=True):
            quoted_column = '"' + column.replace('"', '""') + '"'
            if str(column_type) == "TIMESTAMP WITH TIME ZONE":
                projection.append(
                    "strftime("
                    f"custom_result.{quoted_column} AT TIME ZONE 'UTC', "
                    "'%Y-%m-%dT%H:%M:%SZ'"
                    f") AS {quoted_column}"
                )
            else:
                projection.append(f"custom_result.{quoted_column} AS {quoted_column}")
        projected_sql = ",\n                ".join(projection)
        # DuckDB serializes timestamp-with-time-zone values before Python sees them.
        # This avoids an optional pytz conversion dependency while preserving UTC.
        serialized_rows = connection.execute(
            f"""
            SELECT to_json(projected_result) AS row_json
            FROM (
                SELECT
                    {projected_sql}
                FROM ({sql}) AS custom_result
            ) AS projected_result
            LIMIT {row_limit + 1}
            """
        ).fetchall()
        truncated = len(serialized_rows) > row_limit
        rows = [json.loads(row[0]) for row in serialized_rows[:row_limit]]
        result_pipe.send(
            (
                "ok",
                {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "row_limit": row_limit,
                    "truncated": truncated,
                },
            )
        )
    except Exception as error:
        error_text = str(error).lower()
        error_kind = "external_access" if "file system operations are disabled" in error_text else "query"
        result_pipe.send(("error", error_kind))
    finally:
        if connection is not None:
            connection.close()
        result_pipe.close()


def execute_custom_sql(
    sql: str,
    database_path: Path = DEFAULT_DATABASE_PATH,
    timeout_seconds: float = EXECUTION_TIMEOUT_SECONDS,
    row_limit: int = ROW_LIMIT,
) -> dict[str, Any]:
    """Validate and execute SQL with row, time, access, and process boundaries."""
    validated_sql = validate_sql(sql)
    context = multiprocessing.get_context("spawn")
    receive_pipe, send_pipe = context.Pipe(duplex=False)
    process = context.Process(
        target=_query_worker,
        args=(str(database_path.resolve()), validated_sql, row_limit, send_pipe),
    )
    process.start()
    send_pipe.close()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join()
        receive_pipe.close()
        raise QueryTimeoutError(
            f"Query exceeded the {timeout_seconds:g}-second execution limit."
        )

    if not receive_pipe.poll():
        receive_pipe.close()
        raise QueryExecutionError("Query could not be executed safely.")

    status, payload = receive_pipe.recv()
    receive_pipe.close()
    if status == "ok":
        return payload
    if payload == "external_access":
        raise QueryRejectedError("External file access is disabled.")
    raise QueryExecutionError("Query could not be executed with the allowed read-only features.")
