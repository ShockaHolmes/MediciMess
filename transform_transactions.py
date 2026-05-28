"""Transformation layer for Medici historical transaction data.

This script cleans and transforms raw transaction CSV into analytics-ready data.

Transformations performed:
1. Standardize dates to ISO format (YYYY-MM-DD)
2. Standardize branch names
3. Standardize account names
4. Convert amount fields to numeric (2-decimal strings)
5. Remove duplicate rows (after normalization)
6. Validate that each transaction row is balanced
7. Create cleaned dataset and invalid-record report
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_INPUT = DATA_DIR / "medici_transactions.csv"
DEFAULT_OUTPUT = DATA_DIR / "medici_transactions_cleaned.csv"
DEFAULT_INVALID = DATA_DIR / "medici_transactions_invalid.csv"

REQUIRED_FIELDS = {
    "id",
    "date",
    "branch",
    "type",
    "description",
    "debit_account",
    "debit_amount",
    "credit_account",
    "credit_amount",
}

BRANCH_ALIASES = {
    "firenze": "Florence",
    "florence": "Florence",
    "roma": "Rome",
    "rome": "Rome",
    "venice": "Venice",
    "venezia": "Venice",
    "milan": "Milan",
    "milano": "Milan",
    "geneva": "Geneva",
    "geneve": "Geneva",
    "bruges": "Bruges",
    "london": "London",
    "avignon": "Avignon",
    "constance": "Constance",
    "naples": "Naples",
    "pisa": "Pisa",
}

ACCOUNT_ALIASES = {
    "cash": "Cash",
    "deposits payable": "Deposits Payable",
    "loans receivable": "Loans Receivable",
    "loans receivable - government": "Loans Receivable - Government",
    "interest income": "Interest Income",
    "exchange fee revenue": "Exchange Fee Revenue",
    "trading revenue": "Trading Revenue",
    "accounts payable": "Accounts Payable",
    "wages": "Wages",
    "rent": "Rent",
    "supplies": "Supplies",
    "courier services": "Courier Services",
    "security": "Security",
    "maintenance": "Maintenance",
    "political influence expense": "Political Influence Expense",
    "political receivable": "Political Receivable",
    "papal receivable": "Papal Receivable",
}

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
)


@dataclass
class TransformStats:
    input_rows: int = 0
    cleaned_rows: int = 0
    duplicate_rows_removed: int = 0
    invalid_rows: int = 0


def normalize_space(value: str) -> str:
    return " ".join(value.strip().split())


def standardize_date(raw_value: str) -> str:
    value = normalize_space(raw_value)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"invalid date format: {raw_value!r}")


def standardize_branch(raw_value: str) -> str:
    value = normalize_space(raw_value)
    key = value.casefold()
    if key in BRANCH_ALIASES:
        return BRANCH_ALIASES[key]
    return value.title()


def standardize_account(raw_value: str) -> str:
    value = normalize_space(raw_value)
    if not value:
        return value

    key = value.casefold()
    if key in ACCOUNT_ALIASES:
        return ACCOUNT_ALIASES[key]

    due_from_prefix = "due from "
    loans_prefix = "loans receivable - "

    if key.startswith(due_from_prefix):
        tail = normalize_space(value[len(due_from_prefix):]).title()
        return f"Due from {tail}"

    if key.startswith(loans_prefix):
        tail = normalize_space(value[len(loans_prefix):]).title()
        return f"Loans Receivable - {tail}"

    return value.title()


def parse_positive_amount(value: str, field_name: str) -> Decimal:
    text = normalize_space(value)
    try:
        amount = Decimal(text)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{field_name} is not numeric ({value!r})") from exc

    if amount <= 0:
        raise ValueError(f"{field_name} must be greater than zero ({value!r})")
    return amount.quantize(Decimal("0.01"))


def amount_keys(row: dict[str, str], prefix: str) -> list[str]:
    keys = [k for k in row if k.startswith(f"{prefix}_amount")]
    return sorted(keys, key=lambda k: (len(k), k))


def compute_side_total(row: dict[str, str], side: str) -> Decimal:
    total = Decimal("0")
    for amt_key in amount_keys(row, side):
        suffix = amt_key[len(f"{side}_amount"):]
        account_key = f"{side}_account{suffix}"
        amt_raw = normalize_space(row.get(amt_key, ""))
        acct_raw = normalize_space(row.get(account_key, ""))

        # Empty optional pair is ignored.
        if not amt_raw and not acct_raw:
            continue

        if not amt_raw:
            raise ValueError(f"{amt_key} is empty while {account_key} is present")
        if not acct_raw:
            raise ValueError(f"{account_key} is empty while {amt_key} is present")

        total += parse_positive_amount(amt_raw, amt_key)

    return total


def standardize_row(raw_row: dict[str, str], row_number: int) -> dict[str, str]:
    row = {k: (v if v is not None else "") for k, v in raw_row.items()}

    for field in REQUIRED_FIELDS:
        if not normalize_space(row.get(field, "")):
            raise ValueError(f"missing required field: {field}")

    row["date"] = standardize_date(row["date"])
    row["branch"] = standardize_branch(row["branch"])

    for key in list(row.keys()):
        if key.startswith("debit_account") or key.startswith("credit_account"):
            row[key] = standardize_account(row[key])

    for key in list(row.keys()):
        if key.startswith("debit_amount") or key.startswith("credit_amount"):
            value = normalize_space(row[key])
            if value:
                row[key] = f"{parse_positive_amount(value, key):.2f}"

    debit_total = compute_side_total(row, "debit")
    credit_total = compute_side_total(row, "credit")
    if debit_total != credit_total:
        raise ValueError(
            f"unbalanced transaction at row {row_number}: debits={debit_total} credits={credit_total}"
        )

    # Normalize free-text fields.
    for key in ("type", "counterparty", "description", "currency", "event_name", "recurrence", "trade_good", "branch_to"):
        if key in row:
            row[key] = normalize_space(row[key])

    row["id"] = normalize_space(row["id"])
    return row


def row_signature(row: dict[str, str], columns: list[str]) -> tuple[str, ...]:
    return tuple(row.get(col, "") for col in columns)


def transform_dataset(
    input_path: Path,
    cleaned_output_path: Path,
    invalid_output_path: Path,
) -> int:
    if not input_path.exists():
        print(f"ERROR: input file does not exist: {input_path}")
        return 1

    with input_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        source_columns = list(reader.fieldnames or [])

        missing_columns = sorted(REQUIRED_FIELDS - set(source_columns))
        if missing_columns:
            print("ERROR: input CSV is missing required columns:")
            for column in missing_columns:
                print(f"  - {column}")
            return 1

        cleaned_rows: list[dict[str, str]] = []
        invalid_rows: list[dict[str, Any]] = []
        signatures: set[tuple[str, ...]] = set()
        stats = TransformStats()

        for row_number, raw_row in enumerate(reader, start=2):
            stats.input_rows += 1
            try:
                clean = standardize_row(raw_row, row_number)
                signature = row_signature(clean, source_columns)
                if signature in signatures:
                    stats.duplicate_rows_removed += 1
                    continue
                signatures.add(signature)
                cleaned_rows.append(clean)
            except ValueError as exc:
                stats.invalid_rows += 1
                bad = dict(raw_row)
                bad["_row_number"] = str(row_number)
                bad["_error"] = str(exc)
                invalid_rows.append(bad)

    # Stable ordering for analytics consumption.
    cleaned_rows.sort(key=lambda r: (r.get("date", ""), int(r.get("id", "0") or "0")))
    stats.cleaned_rows = len(cleaned_rows)

    cleaned_output_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_output_path.parent.mkdir(parents=True, exist_ok=True)

    with cleaned_output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=source_columns)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    invalid_columns = source_columns + ["_row_number", "_error"]
    with invalid_output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=invalid_columns)
        writer.writeheader()
        writer.writerows(invalid_rows)

    print("=" * 72)
    print("TRANSFORMATION LAYER SUMMARY")
    print("=" * 72)
    print(f"Input file:             {input_path}")
    print(f"Cleaned output file:    {cleaned_output_path}")
    print(f"Invalid rows file:      {invalid_output_path}")
    print(f"Input rows scanned:     {stats.input_rows:,}")
    print(f"Cleaned rows written:   {stats.cleaned_rows:,}")
    print(f"Duplicates removed:     {stats.duplicate_rows_removed:,}")
    print(f"Invalid rows removed:   {stats.invalid_rows:,}")

    if cleaned_rows:
        dates = [r["date"] for r in cleaned_rows if r.get("date")]
        print(f"Date range in cleaned:  {min(dates)} to {max(dates)}")

    print("=" * 72)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean and transform Medici transaction data into analytics-ready CSV"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Input raw transaction CSV path",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output cleaned CSV path",
    )
    parser.add_argument(
        "--invalid-output",
        default=str(DEFAULT_INVALID),
        help="Output invalid-record CSV path",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return transform_dataset(
        input_path=Path(args.input),
        cleaned_output_path=Path(args.output),
        invalid_output_path=Path(args.invalid_output),
    )


if __name__ == "__main__":
    sys.exit(main())
