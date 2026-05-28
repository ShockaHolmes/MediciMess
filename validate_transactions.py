"""Validate historical transaction CSV data for double-entry consistency.

Checks performed:
1. Required fields are present and non-empty per row.
2. Date format is strict ISO date (YYYY-MM-DD).
3. Debit and credit amounts are valid positive decimals.
4. Each transaction row balances: sum(debits) == sum(credits).
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_CSV = DATA_DIR / "medici_transactions.csv"

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


@dataclass
class InvalidRecord:
    row_number: int
    transaction_id: str
    reasons: list[str]


def _parse_amount(value: str, field_name: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{field_name} is not a valid decimal ({value!r})") from exc
    if amount <= 0:
        raise ValueError(f"{field_name} must be greater than zero ({value!r})")
    return amount


def _collect_side_total(row: dict[str, str], side: str) -> Decimal:
    """Collect total amounts for debit_* or credit_* columns in a row."""
    total = Decimal("0")

    # Base fields are required and handled first.
    base_account_key = f"{side}_account"
    base_amount_key = f"{side}_amount"
    account_value = (row.get(base_account_key) or "").strip()
    amount_value = (row.get(base_amount_key) or "").strip()
    if not account_value:
        raise ValueError(f"{base_account_key} is empty")
    if not amount_value:
        raise ValueError(f"{base_amount_key} is empty")
    total += _parse_amount(amount_value, base_amount_key)

    # Optional split lines: credit_amount_2, debit_amount_2, etc.
    index = 2
    while True:
        amount_key = f"{side}_amount_{index}"
        account_key = f"{side}_account_{index}"
        if amount_key not in row and account_key not in row:
            break

        amount_opt = (row.get(amount_key) or "").strip()
        account_opt = (row.get(account_key) or "").strip()

        if amount_opt or account_opt:
            if not amount_opt:
                raise ValueError(f"{amount_key} is empty")
            if not account_opt:
                raise ValueError(f"{account_key} is empty")
            total += _parse_amount(amount_opt, amount_key)

        index += 1

    return total


def validate_transactions(csv_path: Path, max_invalid_to_print: int = 200) -> int:
    if not csv_path.exists():
        print(f"ERROR: File not found: {csv_path}")
        return 1

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])

        missing_columns = sorted(REQUIRED_FIELDS - fieldnames)
        if missing_columns:
            print("ERROR: Missing required CSV columns:")
            for column in missing_columns:
                print(f"  - {column}")
            return 1

        invalid_records: list[InvalidRecord] = []
        total_rows = 0
        valid_rows = 0
        total_debits = Decimal("0")
        total_credits = Decimal("0")

        for row_number, row in enumerate(reader, start=2):
            total_rows += 1
            reasons: list[str] = []
            tx_id = (row.get("id") or "").strip() or "<missing-id>"

            # Required field non-empty checks.
            for field in sorted(REQUIRED_FIELDS):
                value = (row.get(field) or "").strip()
                if not value:
                    reasons.append(f"{field} is required")

            # Date formatting check.
            date_value = (row.get("date") or "").strip()
            if date_value:
                try:
                    datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError:
                    reasons.append(f"date is not YYYY-MM-DD ({date_value!r})")

            # Amount and balance checks.
            debit_total = Decimal("0")
            credit_total = Decimal("0")
            if not reasons:
                try:
                    debit_total = _collect_side_total(row, "debit")
                    credit_total = _collect_side_total(row, "credit")
                    if debit_total != credit_total:
                        reasons.append(
                            f"unbalanced transaction (debits={debit_total}, credits={credit_total})"
                        )
                except ValueError as exc:
                    reasons.append(str(exc))

            if reasons:
                invalid_records.append(
                    InvalidRecord(
                        row_number=row_number,
                        transaction_id=tx_id,
                        reasons=reasons,
                    )
                )
            else:
                valid_rows += 1
                total_debits += debit_total
                total_credits += credit_total

    invalid_count = len(invalid_records)

    print("=" * 70)
    print("HISTORICAL TRANSACTION VALIDATION")
    print("=" * 70)
    print(f"Dataset: {csv_path}")
    print(f"Rows scanned: {total_rows:,}")
    print(f"Valid rows:   {valid_rows:,}")
    print(f"Invalid rows: {invalid_count:,}")
    print(f"Total debits (valid rows):  {total_debits:,.2f}")
    print(f"Total credits (valid rows): {total_credits:,.2f}")
    print(f"Overall difference:         {abs(total_debits - total_credits):,.2f}")

    if invalid_count:
        print("\nInvalid records:")
        for record in invalid_records[:max_invalid_to_print]:
            reason_text = "; ".join(record.reasons)
            print(
                f"  Row {record.row_number} (id={record.transaction_id}): {reason_text}"
            )

        remaining = invalid_count - max_invalid_to_print
        if remaining > 0:
            print(f"  ... and {remaining} more invalid rows")

    print("\nValidation summary:")
    if invalid_count == 0:
        print("  PASSED: all rows satisfy required fields, dates, amounts, and balancing checks")
        return 0

    print("  FAILED: one or more rows violate validation rules")
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate historical transaction CSV against double-entry checks."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=str(DEFAULT_CSV),
        help="Path to CSV file to validate (default: data/medici_transactions.csv)",
    )
    parser.add_argument(
        "--max-invalid",
        type=int,
        default=200,
        help="Maximum number of invalid records to print",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return validate_transactions(Path(args.csv_path), max_invalid_to_print=args.max_invalid)


if __name__ == "__main__":
    sys.exit(main())
