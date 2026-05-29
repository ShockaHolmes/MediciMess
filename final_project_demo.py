#!/usr/bin/env python3
"""Final project demo for MediciMess.

Labels: demo, presentation, phase-5

This script walks through the full project in one place:
1. Create a ledger
2. Add Medici Bank sample transactions
3. Print transaction logs
4. Print trial balance
5. Print balance sheet
6. Print income statement
7. Export transactions to CSV
8. Export transactions to JSON
9. Print a final success message
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from medici_banking import AccountType, Ledger, TransactionEntry  # noqa: E402

SECTION = "=" * 72
OUTPUT_DIR = PROJECT_ROOT / "data"
CSV_OUTPUT = OUTPUT_DIR / "final_project_demo_transactions.csv"
JSON_OUTPUT = OUTPUT_DIR / "final_project_demo_transactions.json"


def build_demo_ledger() -> tuple[Ledger, dict]:
    """Create the ledger, post the core sample transactions, and snapshot income."""
    ledger = Ledger("Medici Family Bank - Final Demo")
    ledger._silent_mode = True

    # Core chart of accounts used in the demo flow.
    cash = ledger.create_account("Cash", AccountType.ASSET)
    accounts_receivable = ledger.create_account("Accounts Receivable", AccountType.ASSET)
    land = ledger.create_account("Land", AccountType.ASSET)

    capital = ledger.create_account("Owner's Capital", AccountType.EQUITY)
    retained_earnings = ledger.create_account("Retained Earnings", AccountType.EQUITY)
    interest_income = ledger.create_account("Interest Income", AccountType.REVENUE)
    wages = ledger.create_account("Wages", AccountType.EXPENSE)

    transactions = [
        (
            date(1397, 1, 1),
            "Initial investment from Giovanni de' Medici",
            [TransactionEntry.debit(cash, Decimal("10000.00"))],
            [TransactionEntry.credit(capital, Decimal("10000.00"))],
        ),
        (
            date(1397, 2, 15),
            "Loan to Florentine wool merchant",
            [TransactionEntry.debit(accounts_receivable, Decimal("2000.00"))],
            [TransactionEntry.credit(cash, Decimal("2000.00"))],
        ),
        (
            date(1397, 8, 10),
            "Partial loan repayment with interest",
            [TransactionEntry.debit(cash, Decimal("1200.00"))],
            [
                TransactionEntry.credit(accounts_receivable, Decimal("1000.00")),
                TransactionEntry.credit(interest_income, Decimal("200.00")),
            ],
        ),
        (
            date(1397, 9, 5),
            "Purchase of land for the Medici banking house",
            [TransactionEntry.debit(land, Decimal("3000.00"))],
            [TransactionEntry.credit(cash, Decimal("3000.00"))],
        ),
        (
            date(1397, 12, 1),
            "Quarterly wages for bank employees",
            [TransactionEntry.debit(wages, Decimal("800.00"))],
            [TransactionEntry.credit(cash, Decimal("800.00"))],
        ),
    ]

    for tx_date, description, debits, credits in transactions:
        ledger.record_transaction(tx_date, description, *debits, *credits)

    income_statement_report = ledger.get_income_statement_report()

    # Close the period into retained earnings so the balance sheet balances.
    ledger.record_transaction(
        date(1397, 12, 31),
        "Year-end closing entries",
        TransactionEntry.debit(interest_income, Decimal("200.00")),
        TransactionEntry.debit(retained_earnings, Decimal("800.00")),
        TransactionEntry.credit(wages, Decimal("800.00")),
        TransactionEntry.credit(retained_earnings, Decimal("200.00")),
    )

    return ledger, income_statement_report


def print_transaction_logs(ledger: Ledger) -> None:
    """Print a readable log of every transaction in the ledger."""
    print(f"\n{SECTION}")
    print("TRANSACTION LOGS")
    print(SECTION)

    for transaction in ledger.transactions:
        print(f"\nTransaction {transaction.id}: {transaction.date.isoformat()} - {transaction.description}")
        print("  Debits:")
        for entry in transaction.debits:
            print(f"    {entry.account.name:<24} {entry.amount:>12,.2f}")
        print("  Credits:")
        for entry in transaction.credits:
            print(f"    {entry.account.name:<24} {entry.amount:>12,.2f}")


def export_transactions(ledger: Ledger) -> None:
    """Export the final demo ledger to CSV and JSON files."""
    print(f"\n{SECTION}")
    print("EXPORTING TRANSACTIONS")
    print(SECTION)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_count = ledger.export_transactions_to_csv(str(CSV_OUTPUT))
    json_count = ledger.export_transactions_to_json(str(JSON_OUTPUT))

    print(f"Exported {csv_count} transaction(s) to {CSV_OUTPUT.relative_to(PROJECT_ROOT)}")
    print(f"Exported {json_count} transaction(s) to {JSON_OUTPUT.relative_to(PROJECT_ROOT)}")


def print_income_statement_snapshot(report: dict) -> None:
    """Print a saved income statement report."""
    print(f"\n{SECTION}")
    print("INCOME STATEMENT")
    print(SECTION)
    print("INCOME STATEMENT (PRE-CLOSING)")
    print("=" * 60)
    print(f"{'Account':<42} {'Amount (Florins)':>18}")
    print("-" * 60)

    print("REVENUE")
    for row in report["revenue_accounts"]:
        print(f"{row['account_name']:<42} {row['amount']:>18,.2f}")
    print("-" * 60)
    print(f"{'TOTAL REVENUE':<42} {report['total_revenue']:>18,.2f}")
    print()

    print("EXPENSES")
    for row in report["expense_accounts"]:
        print(f"{row['account_name']:<42} {row['amount']:>18,.2f}")
    print("-" * 60)
    print(f"{'TOTAL EXPENSES':<42} {report['total_expenses']:>18,.2f}")
    print()

    net_income = report["net_income"]
    net_label = "NET INCOME"
    if net_income < 0:
        net_label = "NET LOSS"
    elif net_income == 0:
        net_label = "BREAK-EVEN"

    print("SUMMARY")
    print("-" * 60)
    print(f"{'TOTAL REVENUE':<42} {report['total_revenue']:>18,.2f}")
    print(f"{'TOTAL EXPENSES':<42} {report['total_expenses']:>18,.2f}")
    print("=" * 60)
    print(f"{net_label:<42} {net_income:>18,.2f}")


def main() -> int:
    print(f"{SECTION}")
    print("MEDICI MESS - FINAL PROJECT DEMO")
    print("A single walkthrough from ledger creation to reporting and export")
    print(f"{SECTION}")

    print("\nCreating ledger and posting sample transactions...")
    ledger, income_statement_report = build_demo_ledger()

    print_transaction_logs(ledger)

    print(f"\n{SECTION}")
    print("TRIAL BALANCE")
    print(SECTION)
    ledger.print_trial_balance()

    print(f"\n{SECTION}")
    print("BALANCE SHEET")
    print(SECTION)
    ledger.print_balance_sheet()

    print_income_statement_snapshot(income_statement_report)

    export_transactions(ledger)

    print(f"\n{SECTION}")
    print("FINAL SUCCESS")
    print("MediciMess demo completed successfully: ledger, reports, and exports are ready.")
    print(f"{SECTION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
