"""
Medici Bank Additional Dataset Generator (Phase 2)

Expands the historical transaction dataset to more than 80,000 records while
preserving the 1390-1440 coverage window.

This script adds:
- More branch activity
- Recurring operating expenses
- Trade-related transactions
- Loan and repayment transactions
- Vendor payments

Usage:
    /Users/shocka/MediciMess/.venv/bin/python generate_additional_data.py
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

BASE_CSV = DATA_DIR / "medici_transactions.csv"
BASE_JSON = DATA_DIR / "medici_transactions.json"
EXPANDED_CSV = DATA_DIR / "medici_transactions_expanded.csv"
EXPANDED_JSON = DATA_DIR / "medici_transactions_expanded.json"

START_DATE = date(1390, 1, 1)
END_DATE = date(1440, 12, 31)
TARGET_TOTAL = 85000


class AdditionalTransactionGenerator:
    """Generate additional transactions to expand the historical dataset."""

    def __init__(self, seed: int = 31415):
        random.seed(seed)
        self.branches = [
            "Florence",
            "Rome",
            "Venice",
            "Milan",
            "Geneva",
            "Bruges",
            "London",
            "Avignon",
            "Naples",
            "Pisa",
        ]
        self.merchants = [
            "Wool Guild Syndicate",
            "Silk Consortium",
            "Levant Spice Traders",
            "Flemish Cloth House",
            "Venetian Grain Brokers",
            "Lombard Metals Exchange",
            "Tuscan Wine Carriers",
            "Mediterranean Shipping Company",
        ]
        self.vendors = [
            "Santa Maria Scribes",
            "Florentine Paperworks",
            "Guildhall Security Company",
            "San Lorenzo Couriers",
            "Arno Lamp Oil Merchants",
            "Mercato Maintenance Works",
            "Ponte Vecchio Rent Office",
            "Signoria Utilities Office",
        ]
        self.nobles = [
            "Duke of Milan",
            "Doge of Venice",
            "Republic of Florence",
            "Kingdom of Naples",
            "Count of Urbino",
            "Marquis of Mantua",
        ]
        self.trade_goods = [
            "wool",
            "silk",
            "spices",
            "alum",
            "grain",
            "wine",
            "dyestuffs",
            "metals",
        ]

    @staticmethod
    def random_date(start: date, end: date) -> date:
        delta = end - start
        return start + timedelta(days=random.randint(0, delta.days))

    @staticmethod
    def random_amount(min_amount: int, max_amount: int) -> Decimal:
        base = random.uniform(min_amount, max_amount)
        factor = random.choice([1, 1, 1, 2, 5, 10])
        return Decimal(str(base * factor)).quantize(Decimal("0.01"))

    def generate_branch_activity(self, transaction_id: int) -> dict[str, Any]:
        src = random.choice(self.branches)
        dst = random.choice([b for b in self.branches if b != src])
        amount = self.random_amount(200, 18000)
        fee = (amount * Decimal("0.015")).quantize(Decimal("0.01"))
        tx_date = self.random_date(START_DATE, END_DATE)
        return {
            "id": transaction_id,
            "date": tx_date.isoformat(),
            "branch": src,
            "branch_to": dst,
            "type": "branch_activity",
            "counterparty": f"Inter-branch transfer to {dst}",
            "description": f"Branch settlement transfer from {src} to {dst}",
            "debit_account": f"Due from {dst}",
            "debit_amount": float(amount),
            "credit_account": "Cash",
            "credit_amount": float((amount - fee).quantize(Decimal("0.01"))),
            "credit_account_2": "Exchange Fee Revenue",
            "credit_amount_2": float(fee),
            "currency": "florin",
        }

    def generate_recurring_operating_expense(self, transaction_id: int) -> dict[str, Any]:
        branch = random.choice(self.branches)
        expense = random.choice([
            ("Wages", "monthly"),
            ("Rent", "monthly"),
            ("Supplies", "monthly"),
            ("Security", "monthly"),
            ("Courier Services", "weekly"),
            ("Maintenance", "quarterly"),
        ])
        amount = self.random_amount(50, 2400)
        tx_date = self.random_date(START_DATE, END_DATE)
        vendor = random.choice(self.vendors)
        return {
            "id": transaction_id,
            "date": tx_date.isoformat(),
            "branch": branch,
            "type": "recurring_operating_expense",
            "counterparty": vendor,
            "description": f"{expense[0]} expense for {branch} branch ({expense[1]} cycle)",
            "debit_account": expense[0],
            "debit_amount": float(amount),
            "credit_account": "Cash",
            "credit_amount": float(amount),
            "recurrence": expense[1],
            "currency": "florin",
        }

    def generate_trade_transaction(self, transaction_id: int) -> dict[str, Any]:
        branch = random.choice(self.branches)
        good = random.choice(self.trade_goods)
        merchant = random.choice(self.merchants)
        amount = self.random_amount(150, 22000)
        tx_date = self.random_date(START_DATE, END_DATE)
        return {
            "id": transaction_id,
            "date": tx_date.isoformat(),
            "branch": branch,
            "type": "trade_transaction",
            "counterparty": merchant,
            "description": f"Trade finance settlement for {good} cargo",
            "debit_account": "Cash",
            "debit_amount": float(amount),
            "credit_account": "Trading Revenue",
            "credit_amount": float(amount),
            "trade_good": good,
            "currency": "florin",
        }

    def generate_loan_issuance(self, transaction_id: int) -> dict[str, Any]:
        branch = random.choice(self.branches)
        borrower = random.choice(self.merchants + self.nobles)
        amount = self.random_amount(300, 120000)
        tx_date = self.random_date(START_DATE, END_DATE)
        return {
            "id": transaction_id,
            "date": tx_date.isoformat(),
            "branch": branch,
            "type": "loan_issuance",
            "counterparty": borrower,
            "description": f"Commercial loan issued to {borrower}",
            "debit_account": "Loans Receivable",
            "debit_amount": float(amount),
            "credit_account": "Cash",
            "credit_amount": float(amount),
            "currency": "florin",
        }

    def generate_loan_repayment(self, transaction_id: int) -> dict[str, Any]:
        branch = random.choice(self.branches)
        borrower = random.choice(self.merchants + self.nobles)
        principal = self.random_amount(150, 45000)
        rate = Decimal(random.choice(["0.08", "0.10", "0.12", "0.15", "0.18", "0.22"]))
        interest = (principal * rate).quantize(Decimal("0.01"))
        total = principal + interest
        tx_date = self.random_date(START_DATE, END_DATE)
        return {
            "id": transaction_id,
            "date": tx_date.isoformat(),
            "branch": branch,
            "type": "loan_repayment",
            "counterparty": borrower,
            "description": f"Loan repayment from {borrower} including interest",
            "debit_account": "Cash",
            "debit_amount": float(total),
            "credit_account": "Loans Receivable",
            "credit_amount": float(principal),
            "credit_account_2": "Interest Income",
            "credit_amount_2": float(interest),
            "currency": "florin",
        }

    def generate_vendor_payment(self, transaction_id: int) -> dict[str, Any]:
        branch = random.choice(self.branches)
        vendor = random.choice(self.vendors)
        amount = self.random_amount(80, 9000)
        tx_date = self.random_date(START_DATE, END_DATE)
        return {
            "id": transaction_id,
            "date": tx_date.isoformat(),
            "branch": branch,
            "type": "vendor_payment",
            "counterparty": vendor,
            "description": f"Vendor payment to {vendor} for branch services",
            "debit_account": "Accounts Payable",
            "debit_amount": float(amount),
            "credit_account": "Cash",
            "credit_amount": float(amount),
            "currency": "florin",
        }

    def generate_transactions(self, start_id: int, count: int) -> list[dict[str, Any]]:
        generated: list[dict[str, Any]] = []
        next_id = start_id

        weighted_types = [
            ("branch_activity", 0.22),
            ("recurring_operating_expense", 0.20),
            ("trade_transaction", 0.18),
            ("loan_issuance", 0.15),
            ("loan_repayment", 0.15),
            ("vendor_payment", 0.10),
        ]

        # Guarantee at least one of each required category.
        required = [
            self.generate_branch_activity,
            self.generate_recurring_operating_expense,
            self.generate_trade_transaction,
            self.generate_loan_issuance,
            self.generate_loan_repayment,
            self.generate_vendor_payment,
        ]
        for factory in required:
            generated.append(factory(next_id))
            next_id += 1

        while len(generated) < count:
            draw = random.random()
            cumulative = 0.0
            tx_type = "branch_activity"
            for name, weight in weighted_types:
                cumulative += weight
                if draw <= cumulative:
                    tx_type = name
                    break

            if tx_type == "branch_activity":
                tx = self.generate_branch_activity(next_id)
            elif tx_type == "recurring_operating_expense":
                tx = self.generate_recurring_operating_expense(next_id)
            elif tx_type == "trade_transaction":
                tx = self.generate_trade_transaction(next_id)
            elif tx_type == "loan_issuance":
                tx = self.generate_loan_issuance(next_id)
            elif tx_type == "loan_repayment":
                tx = self.generate_loan_repayment(next_id)
            else:
                tx = self.generate_vendor_payment(next_id)

            generated.append(tx)
            next_id += 1

        generated.sort(key=lambda r: (r["date"], int(r["id"])))
        return generated[:count]


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array in {path}")
    return data


def normalize_ids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_sorted = sorted(rows, key=lambda r: (r.get("date", ""), int(r.get("id", 0))))
    for idx, row in enumerate(rows_sorted, start=1):
        row["id"] = idx
    return rows_sorted


def save_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames: set[str] = set()
    for row in rows:
        fieldnames.update(row.keys())
    ordered = sorted(fieldnames)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def summarize(rows: list[dict[str, Any]]) -> None:
    dates = [r.get("date", "") for r in rows if r.get("date")]
    type_counts = Counter(r.get("type", "unknown") for r in rows)
    branch_counts = Counter(r.get("branch", "unknown") for r in rows)

    print("\n" + "=" * 64)
    print("EXPANDED DATASET SUMMARY")
    print("=" * 64)
    print(f"Total transactions: {len(rows):,}")
    if dates:
        print(f"Date range: {min(dates)} to {max(dates)}")
    print("\nTop transaction types:")
    for tx_type, count in type_counts.most_common(10):
        print(f"  {tx_type:30s} {count:7d}")

    print("\nTop branches:")
    for branch, count in branch_counts.most_common(10):
        print(f"  {branch:30s} {count:7d}")
    print("=" * 64)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    base_csv_rows = load_csv(BASE_CSV)
    base_json_rows = load_json(BASE_JSON)

    # Prefer JSON base for richer typed values, but keep parity check with CSV count.
    base_rows: list[dict[str, Any]] = [dict(r) for r in base_json_rows]
    if len(base_csv_rows) != len(base_rows):
        print(
            "Warning: CSV/JSON base counts differ "
            f"({len(base_csv_rows)} vs {len(base_rows)}). Continuing with JSON base."
        )

    current_total = len(base_rows)
    add_count = max(0, TARGET_TOTAL - current_total)

    print("Expanding Medici historical dataset...")
    print(f"Current transaction count: {current_total:,}")
    print(f"Target transaction count:  {TARGET_TOTAL:,}")
    print(f"Additional to generate:    {add_count:,}")

    if add_count == 0:
        expanded_rows = normalize_ids(base_rows)
    else:
        max_id = max(int(r.get("id", 0)) for r in base_rows) if base_rows else 0
        generator = AdditionalTransactionGenerator(seed=2718)
        new_rows = generator.generate_transactions(start_id=max_id + 1, count=add_count)
        expanded_rows = normalize_ids(base_rows + new_rows)

    # Guarantee the expected date-window coverage in final output.
    dates = [r.get("date", "") for r in expanded_rows if r.get("date")]
    if not dates or min(dates) > START_DATE.isoformat() or max(dates) < END_DATE.isoformat():
        print("Warning: dataset date range does not fully cover 1390-1440.")

    # Save canonical updated files plus explicit expanded snapshots.
    save_csv(expanded_rows, BASE_CSV)
    save_json(expanded_rows, BASE_JSON)
    save_csv(expanded_rows, EXPANDED_CSV)
    save_json(expanded_rows, EXPANDED_JSON)

    summarize(expanded_rows)
    print("\nSaved files:")
    print(f"  - {BASE_CSV}")
    print(f"  - {BASE_JSON}")
    print(f"  - {EXPANDED_CSV}")
    print(f"  - {EXPANDED_JSON}")


if __name__ == "__main__":
    main()
