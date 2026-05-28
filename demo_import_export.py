#!/usr/bin/env python3
"""
demo_import_export.py — Import/Export Demo Script
Labels: demo, data-import, data-export, phase-2

Demonstrates the Medici Banking data pipeline:
  1. Build a sample ledger and record transactions
  2. Export to CSV  (data/demo_transactions.csv)
  3. Export to JSON (data/demo_transactions.json)
  4. Import CSV into a fresh ledger and print trial balance
  5. Import JSON into a fresh ledger and print trial balance
"""

import sys
from pathlib import Path
from decimal import Decimal
from datetime import date

# Support running from the project root or the src/ directory.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from medici_banking import AccountType, Ledger, TransactionEntry  # noqa: E402

SECTION = "=" * 70


# ---------------------------------------------------------------------------
# Step 1 — Build the sample ledger
# ---------------------------------------------------------------------------

def build_sample_ledger() -> Ledger:
    """Create a Medici branch ledger with representative transactions."""
    print(SECTION)
    print("STEP 1: BUILDING SAMPLE LEDGER")
    print(SECTION)

    ledger = Ledger("Medici Bank — Florence Branch")

    # Accounts
    cash         = ledger.create_account("Cash",                AccountType.ASSET)
    receivable   = ledger.create_account("Accounts Receivable", AccountType.ASSET)
    land         = ledger.create_account("Land",                AccountType.ASSET)
    wages_exp    = ledger.create_account("Wages Expense",       AccountType.EXPENSE)
    interest_rev = ledger.create_account("Interest Income",     AccountType.REVENUE)
    capital      = ledger.create_account("Owner's Capital",     AccountType.EQUITY)

    # Transactions
    transactions = [
        (
            date(1397, 1, 1),
            "Initial capital investment by Giovanni de' Medici",
            [TransactionEntry.debit(cash, Decimal("10000.00"))],
            [TransactionEntry.credit(capital, Decimal("10000.00"))],
        ),
        (
            date(1397, 2, 15),
            "Loan extended to Florentine wool merchant",
            [TransactionEntry.debit(receivable, Decimal("2000.00"))],
            [TransactionEntry.credit(cash, Decimal("2000.00"))],
        ),
        (
            date(1397, 8, 10),
            "Partial loan repayment with interest from wool merchant",
            [TransactionEntry.debit(cash, Decimal("1200.00"))],
            [
                TransactionEntry.credit(receivable,   Decimal("1000.00")),
                TransactionEntry.credit(interest_rev, Decimal("200.00")),
            ],
        ),
        (
            date(1397, 9, 5),
            "Purchase of land for new Medici banking house",
            [TransactionEntry.debit(land, Decimal("3000.00"))],
            [TransactionEntry.credit(cash, Decimal("3000.00"))],
        ),
        (
            date(1397, 12, 1),
            "Quarterly wages for bank employees",
            [TransactionEntry.debit(wages_exp, Decimal("800.00"))],
            [TransactionEntry.credit(cash, Decimal("800.00"))],
        ),
    ]

    for tx_date, description, debits, credits in transactions:
        ledger.record_transaction(tx_date, description, *debits, *credits)
        print(f"  Posted [{tx_date}]  {description}")

    print(f"\n  {len(ledger.transactions)} transactions recorded across "
          f"{len(ledger.accounts)} accounts.")
    return ledger


# ---------------------------------------------------------------------------
# Step 2 — Export to CSV and JSON
# ---------------------------------------------------------------------------

def export_ledger(ledger: Ledger) -> tuple[Path, Path]:
    """Export the ledger to both CSV and JSON, returning the file paths."""
    print(f"\n{SECTION}")
    print("STEP 2: EXPORTING TRANSACTIONS")
    print(SECTION)

    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    csv_path  = data_dir / "demo_transactions.csv"
    json_path = data_dir / "demo_transactions.json"

    csv_count  = ledger.export_transactions_to_csv(str(csv_path))
    json_count = ledger.export_transactions_to_json(str(json_path))

    print(f"  Exported {csv_count}  transactions -> {csv_path.relative_to(PROJECT_ROOT)}")
    print(f"  Exported {json_count} transactions -> {json_path.relative_to(PROJECT_ROOT)}")

    return csv_path, json_path


# ---------------------------------------------------------------------------
# Step 3 — Import CSV into a fresh ledger
# ---------------------------------------------------------------------------

def import_from_csv(csv_path: Path) -> Ledger:
    """Import transactions from a CSV file and verify with a trial balance."""
    print(f"\n{SECTION}")
    print("STEP 3: IMPORTING FROM CSV")
    print(SECTION)

    ledger = Ledger("CSV Import Ledger")
    print(f"\n  Source: {csv_path.relative_to(PROJECT_ROOT)}")

    count = ledger.import_transactions_from_csv(str(csv_path), verbose=True)
    print(f"\n  Imported {count} transaction(s) into '{ledger.name}'.")

    print(f"\n{'- ' * 35}")
    print("  TRIAL BALANCE — CSV Import Ledger")
    print(f"{'- ' * 35}")
    ledger.print_trial_balance()

    return ledger


# ---------------------------------------------------------------------------
# Step 4 — Import JSON into a fresh ledger
# ---------------------------------------------------------------------------

def import_from_json(json_path: Path) -> Ledger:
    """Import transactions from a JSON file and verify with a trial balance."""
    print(f"\n{SECTION}")
    print("STEP 4: IMPORTING FROM JSON")
    print(SECTION)

    ledger = Ledger("JSON Import Ledger")
    print(f"\n  Source: {json_path.relative_to(PROJECT_ROOT)}")

    count = ledger.import_transactions_from_json(str(json_path), verbose=True)
    print(f"\n  Imported {count} transaction(s) into '{ledger.name}'.")

    print(f"\n{'- ' * 35}")
    print("  TRIAL BALANCE — JSON Import Ledger")
    print(f"{'- ' * 35}")
    ledger.print_trial_balance()

    return ledger


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n{'#' * 70}")
    print("# MEDICI BANK — IMPORT / EXPORT DEMO")
    print(f"{'#' * 70}\n")

    # 1. Build sample data
    source_ledger = build_sample_ledger()

    # 2. Export CSV + JSON
    csv_path, json_path = export_ledger(source_ledger)

    # 3. Import CSV → trial balance
    import_from_csv(csv_path)

    # 4. Import JSON → trial balance
    import_from_json(json_path)

    print(f"\n{'#' * 70}")
    print("# DEMO COMPLETE")
    print(f"{'#' * 70}")
    print("""
Quick reference — use these methods in your own code:

  count = ledger.export_transactions_to_csv("data/my_export.csv")
  count = ledger.export_transactions_to_json("data/my_export.json")
  count = ledger.import_transactions_from_csv("data/my_export.csv", verbose=True)
  count = ledger.import_transactions_from_json("data/my_export.json", verbose=True)
""")


if __name__ == "__main__":
    main()
