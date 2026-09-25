"""Generate the deterministic synthetic Merchant Portfolio Monitor dataset."""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


SEED = 20260924
AS_OF = datetime(2026, 9, 24, 0, 0, 0, tzinfo=timezone.utc)
MERCHANT_COUNT = 200
TRANSACTIONS_PER_MERCHANT = 1_000

PLANTED_MERCHANTS = {
    "chargeback_spike": "M0001",
    "card_testing_burst": "M0002",
    "refund_abuse": "M0003",
    "below_review_limit": "M0004",
    "shared_bank_account": "M0005",
    "dormant_suddenly_active": "M0006",
    "volume_above_declared": "M0007",
    "ticket_size_jump": "M0008",
}

DECOY_MERCHANTS = {
    "seasonal_volume_spike": "M0198",
    "event_cancellation_refunds": "M0199",
    "contract_ticket_increase": "M0200",
}

MERCHANT_FIELDS = (
    "merchant_id",
    "merchant_name",
    "created_at",
    "category",
    "region",
    "declared_monthly_volume_cents",
    "typical_ticket_cents",
    "bank_account_token",
    "owner_phone_token",
    "address_token",
    "is_planted",
    "planted_issue",
    "is_decoy",
    "decoy_scenario",
)

TRANSACTION_FIELDS = (
    "transaction_id",
    "merchant_id",
    "occurred_at",
    "amount_cents",
    "status",
    "card_token",
    "ip_token",
    "currency",
)

REFUND_FIELDS = (
    "refund_id",
    "transaction_id",
    "merchant_id",
    "occurred_at",
    "amount_cents",
    "reason",
)

CHARGEBACK_FIELDS = (
    "chargeback_id",
    "transaction_id",
    "merchant_id",
    "occurred_at",
    "amount_cents",
    "reason",
)


def utc_text(value: datetime) -> str:
    """Return a stable second-precision UTC timestamp."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bounded_time_after(occurred_at: datetime, days: int) -> datetime:
    """Place a related event after a transaction without crossing the as-of date."""
    return min(occurred_at + timedelta(days=days), AS_OF - timedelta(minutes=1))


def random_time(
    rng: random.Random,
    start: datetime,
    end: datetime,
) -> datetime:
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(seconds + 1))


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, object]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def merchant_rows() -> list[dict[str, object]]:
    categories = (
        "apparel",
        "digital_goods",
        "home_services",
        "restaurants",
        "health_beauty",
        "professional_services",
    )
    regions = ("north", "south", "east", "west")
    planted_by_id = {merchant_id: issue for issue, merchant_id in PLANTED_MERCHANTS.items()}
    decoy_by_id = {merchant_id: scenario for scenario, merchant_id in DECOY_MERCHANTS.items()}
    rows: list[dict[str, object]] = []

    for number in range(1, MERCHANT_COUNT + 1):
        merchant_id = f"M{number:04d}"
        category = categories[(number - 1) % len(categories)]
        declared_volume = 9_000_000 + (number % 13) * 750_000
        typical_ticket = 4_000 + (number % 9) * 650
        created_at = AS_OF - timedelta(days=730 - number)
        bank_token = f"bank_synthetic_{number:04d}"

        if merchant_id == "M0005":
            bank_token = "bank_synthetic_shared_0005"
            created_at = AS_OF - timedelta(days=120)
        elif merchant_id == "M0100":
            bank_token = "bank_synthetic_shared_0005"
            created_at = AS_OF - timedelta(days=900)
        elif merchant_id == "M0007":
            declared_volume = 2_000_000
        elif merchant_id == "M0198":
            category = "seasonal_gifts"
            declared_volume = 80_000_000
        elif merchant_id == "M0199":
            category = "ticketed_events"
            declared_volume = 35_000_000
        elif merchant_id == "M0200":
            category = "business_wholesale"
            declared_volume = 100_000_000
            typical_ticket = 40_000

        planted_issue = planted_by_id.get(merchant_id, "")
        decoy_scenario = decoy_by_id.get(merchant_id, "")
        rows.append(
            {
                "merchant_id": merchant_id,
                "merchant_name": f"Synthetic Merchant {number:04d}",
                "created_at": utc_text(created_at),
                "category": category,
                "region": regions[(number - 1) % len(regions)],
                "declared_monthly_volume_cents": declared_volume,
                "typical_ticket_cents": typical_ticket,
                "bank_account_token": bank_token,
                "owner_phone_token": f"phone_synthetic_{number:04d}",
                "address_token": f"address_synthetic_{number:04d}",
                "is_planted": str(bool(planted_issue)).lower(),
                "planted_issue": planted_issue,
                "is_decoy": str(bool(decoy_scenario)).lower(),
                "decoy_scenario": decoy_scenario,
            }
        )

    return rows


def transaction_values(
    merchant_id: str,
    index: int,
    typical_ticket: int,
    rng: random.Random,
) -> tuple[datetime, int, str, str, str]:
    """Return timestamp, amount, status, card token, and IP token."""
    start = AS_OF - timedelta(days=180)
    end = AS_OF - timedelta(minutes=2)
    occurred_at = random_time(rng, start, end)
    amount = max(100, int(rng.gauss(typical_ticket, typical_ticket * 0.3)))
    status_roll = rng.random()
    status = "approved" if status_roll < 0.93 else "declined" if status_roll < 0.98 else "reversed"
    card_token = f"card_synthetic_{rng.randrange(1, 50001):05d}"
    ip_token = f"ip_synthetic_{rng.randrange(1, 12001):05d}"

    if merchant_id == "M0001":
        if index < 120:
            occurred_at = AS_OF - timedelta(days=6) + timedelta(minutes=index * 47)
            status = "approved"
        elif index < 220:
            occurred_at = AS_OF - timedelta(days=90) + timedelta(minutes=index * 31)
            status = "approved"
    elif merchant_id == "M0002" and index < 300:
        occurred_at = AS_OF - timedelta(days=2, hours=3) + timedelta(seconds=index * 10)
        amount = 100 + index % 100
        status = "declined" if index % 5 else "approved"
        card_token = f"card_test_synthetic_{index:04d}"
        ip_token = "ip_synthetic_card_test_source"
    elif merchant_id == "M0004" and index < 400:
        occurred_at = AS_OF - timedelta(days=29) + timedelta(minutes=index * 90)
        amount = 9_900 + index % 100
        status = "approved"
    elif merchant_id == "M0006":
        if index < 700:
            occurred_at = random_time(rng, AS_OF - timedelta(days=180), AS_OF - timedelta(days=120))
        else:
            occurred_at = random_time(rng, AS_OF - timedelta(days=3), end)
        status = "approved"
    elif merchant_id == "M0007":
        occurred_at = random_time(rng, AS_OF - timedelta(days=29), end)
        amount = 50_000 + index % 20_000
        status = "approved"
    elif merchant_id == "M0008":
        if index < 800:
            occurred_at = random_time(rng, start, AS_OF - timedelta(days=8))
            amount = 4_500 + index % 1_000
        else:
            occurred_at = random_time(rng, AS_OF - timedelta(days=7), end)
            amount = 35_000 + index % 10_000
        status = "approved"
    elif merchant_id == "M0198":
        if index < 550:
            occurred_at = random_time(rng, AS_OF - timedelta(days=14), end)
        else:
            occurred_at = random_time(rng, AS_OF - timedelta(days=180), AS_OF - timedelta(days=60))
        amount = 7_000 + index % 4_000
        status = "approved"
    elif merchant_id == "M0200":
        if index < 180:
            occurred_at = random_time(rng, AS_OF - timedelta(days=7), end)
            amount = 55_000 + index % 15_000
        else:
            occurred_at = random_time(rng, start, AS_OF - timedelta(days=8))
            amount = 12_000 + index % 6_000
        status = "approved"

    return occurred_at, amount, status, card_token, ip_token


def generate_dataset(output_dir: Path) -> dict[str, object]:
    """Create all dataset files and return their manifest."""
    rng = random.Random(SEED)
    output_dir = output_dir.resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}_staging"

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    merchants = merchant_rows()
    merchant_count = write_csv(staging_dir / "merchants.csv", MERCHANT_FIELDS, merchants)
    merchant_lookup = {row["merchant_id"]: row for row in merchants}

    approved_by_merchant: dict[str, list[tuple[str, datetime, int]]] = {
        merchant_id: [] for merchant_id in merchant_lookup
    }
    transaction_count = 0
    with (staging_dir / "transactions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRANSACTION_FIELDS, lineterminator="\n")
        writer.writeheader()
        for merchant_number in range(1, MERCHANT_COUNT + 1):
            merchant_id = f"M{merchant_number:04d}"
            typical_ticket = int(merchant_lookup[merchant_id]["typical_ticket_cents"])
            for index in range(TRANSACTIONS_PER_MERCHANT):
                transaction_id = f"T{transaction_count + 1:09d}"
                occurred_at, amount, status, card_token, ip_token = transaction_values(
                    merchant_id, index, typical_ticket, rng
                )
                writer.writerow(
                    {
                        "transaction_id": transaction_id,
                        "merchant_id": merchant_id,
                        "occurred_at": utc_text(occurred_at),
                        "amount_cents": amount,
                        "status": status,
                        "card_token": card_token,
                        "ip_token": ip_token,
                        "currency": "USD",
                    }
                )
                if status == "approved":
                    approved_by_merchant[merchant_id].append((transaction_id, occurred_at, amount))
                transaction_count += 1

    refund_rows: list[dict[str, object]] = []
    refund_reasons = ("customer_request", "duplicate", "item_returned", "service_issue")
    for merchant_id, transactions in approved_by_merchant.items():
        target_count = 250 if merchant_id == "M0003" else 180 if merchant_id == "M0199" else 10
        reason = "event_cancelled" if merchant_id == "M0199" else None
        for transaction_id, occurred_at, amount in transactions[:target_count]:
            refund_rows.append(
                {
                    "refund_id": f"R{len(refund_rows) + 1:07d}",
                    "transaction_id": transaction_id,
                    "merchant_id": merchant_id,
                    "occurred_at": utc_text(bounded_time_after(occurred_at, 2)),
                    "amount_cents": amount if merchant_id in {"M0003", "M0199"} else max(100, amount // 2),
                    "reason": reason or refund_reasons[len(refund_rows) % len(refund_reasons)],
                }
            )
    refund_count = write_csv(staging_dir / "refunds.csv", REFUND_FIELDS, refund_rows)

    chargeback_rows: list[dict[str, object]] = []
    chargeback_reasons = ("fraud", "not_recognized", "product_not_received")
    for merchant_id, transactions in approved_by_merchant.items():
        if merchant_id == "M0001":
            recent = [item for item in transactions if item[1] >= AS_OF - timedelta(days=7)]
            older = [item for item in transactions if item[1] < AS_OF - timedelta(days=30)]
            selected = recent[:50] + older[:3]
        else:
            selected = transactions[:2]
        for transaction_id, occurred_at, amount in selected:
            chargeback_rows.append(
                {
                    "chargeback_id": f"C{len(chargeback_rows) + 1:07d}",
                    "transaction_id": transaction_id,
                    "merchant_id": merchant_id,
                    "occurred_at": utc_text(bounded_time_after(occurred_at, 7)),
                    "amount_cents": amount,
                    "reason": chargeback_reasons[len(chargeback_rows) % len(chargeback_reasons)],
                }
            )
    chargeback_count = write_csv(
        staging_dir / "chargebacks.csv", CHARGEBACK_FIELDS, chargeback_rows
    )

    manifest: dict[str, object] = {
        "as_of_utc": utc_text(AS_OF),
        "seed": SEED,
        "row_counts": {
            "merchants": merchant_count,
            "transactions": transaction_count,
            "refunds": refund_count,
            "chargebacks": chargeback_count,
        },
        "planted_merchants": PLANTED_MERCHANTS,
        "decoy_merchants": DECOY_MERCHANTS,
    }
    with (staging_dir / "manifest.json").open("w", encoding="utf-8", newline="") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    return manifest


def print_summary(manifest: dict[str, object]) -> None:
    counts = manifest["row_counts"]
    assert isinstance(counts, dict)
    print("Synthetic dataset generated")
    print(f"As-of: {manifest['as_of_utc']}")
    print(
        "Rows: "
        + ", ".join(f"{name}={count:,}" for name, count in counts.items() if isinstance(count, int))
    )
    planted = manifest["planted_merchants"]
    assert isinstance(planted, dict)
    print("Planted merchants: " + ", ".join(f"{issue}={merchant_id}" for issue, merchant_id in planted.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Directory for generated CSV files and the manifest.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_dataset(args.output_dir)
    print_summary(manifest)


if __name__ == "__main__":
    main()
