"""Load and execute the allowlisted portfolio-monitoring SQL queries."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.database import DEFAULT_DATABASE_PATH, get_read_only_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUERY_DIR = PROJECT_ROOT / "queries"
QUERY_NAMES = (
    "chargeback_spike",
    "card_testing_burst",
    "refund_abuse",
    "below_review_limit",
    "shared_bank_account",
    "dormant_suddenly_active",
    "volume_above_declared",
    "ticket_size_jump",
    "portfolio_summary",
    "decline_rate_outliers",
    "shared_merchant_attributes",
    "volume_concentration",
)

REQUIRED_HEADER_FIELDS = (
    "title",
    "category",
    "severity",
    "what_it_flags",
    "why_it_matters",
    "logic",
    "thresholds",
    "likely_false_positives",
    "next_step",
    "output_columns",
    "data_notes",
)

ALLOWED_CATEGORIES = {
    "Disputes",
    "Velocity",
    "Refunds",
    "Activity Change",
    "Structuring",
    "Linkage",
    "Portfolio",
}
ALLOWED_SEVERITIES = {"High", "Medium", "Low"}


def parse_header(sql: str) -> dict[str, str]:
    """Parse the standard leading SQL comment block into normalized fields."""
    metadata: dict[str, str] = {}
    for line in sql.splitlines():
        if not line.startswith("-- "):
            break
        key, separator, value = line[3:].partition(":")
        if separator:
            normalized_key = key.strip().lower().replace(" ", "_")
            metadata[normalized_key] = value.strip()
    return metadata


def load_query(query_name: str) -> dict[str, str]:
    """Load metadata and SQL only for a known query name."""
    if query_name not in QUERY_NAMES:
        raise KeyError(query_name)
    sql = (QUERY_DIR / f"{query_name}.sql").read_text(encoding="utf-8")
    metadata = parse_header(sql)
    missing_fields = [field for field in REQUIRED_HEADER_FIELDS if not metadata.get(field)]
    if missing_fields:
        raise ValueError(f"Query {query_name} is missing header fields: {', '.join(missing_fields)}")

    severity, separator, severity_reason = metadata["severity"].partition("|")
    severity = severity.strip()
    severity_reason = severity_reason.strip()
    if severity not in ALLOWED_SEVERITIES or not separator or not severity_reason:
        raise ValueError(f"Query {query_name} has an invalid Severity field")
    if metadata["category"] not in ALLOWED_CATEGORIES:
        raise ValueError(f"Query {query_name} has an invalid Category field")

    return {
        "name": query_name,
        "title": metadata["title"],
        "description": metadata["what_it_flags"],
        "category": metadata["category"],
        "severity": severity,
        "severity_reason": severity_reason,
        "why_it_matters": metadata["why_it_matters"],
        "next_step": metadata["next_step"],
        "sql": sql,
    }


def list_queries() -> list[dict[str, str]]:
    """Return display metadata for all currently available queries."""
    return [
        {
            "name": query["name"],
            "title": query["title"],
            "description": query["description"],
            "category": query["category"],
            "severity": query["severity"],
            "severity_reason": query["severity_reason"],
            "why_it_matters": query["why_it_matters"],
            "next_step": query["next_step"],
        }
        for query in (load_query(query_name) for query_name in QUERY_NAMES)
    ]


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def run_query(
    query_name: str,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> dict[str, Any]:
    """Execute one trusted named query through a read-only connection."""
    query = load_query(query_name)
    connection = get_read_only_connection(database_path)
    try:
        cursor = connection.execute(query["sql"])
        columns = [column[0] for column in cursor.description]
        rows = [
            {column: json_value(value) for column, value in zip(columns, row, strict=True)}
            for row in cursor.fetchall()
        ]
    finally:
        connection.close()
    return {
        **query,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }
