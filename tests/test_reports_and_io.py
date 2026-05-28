"""Tests for the balance sheet report and JSON import/export batches."""

"""This is written for the seed data could you ask copilot to write it to test from our actual data?"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from medici_banking import Ledger, AccountType, TransactionEntry


def _seed_ledger():
    led = Ledger("Test Bank")
    led._silent_mode = True
    cash = led.create_account("Cash", AccountType.ASSET)
    land = led.create_account("Land", AccountType.ASSET)
    loans = led.create_account("Loans", AccountType.LIABILITY)
    capital = led.create_account("Capital", AccountType.EQUITY)
    revenue = led.create_account("Interest Income", AccountType.REVENUE)
    wages = led.create_account("Wages", AccountType.EXPENSE)

    led.record_transaction(date(1397, 1, 1), "Investment",
        TransactionEntry.debit(cash, Decimal("10000")),
        TransactionEntry.credit(capital, Decimal("10000")))
    led.record_transaction(date(1397, 2, 1), "Take a loan",
        TransactionEntry.debit(cash, Decimal("2000")),
        TransactionEntry.credit(loans, Decimal("2000")))
    led.record_transaction(date(1397, 3, 1), "Buy land",
        TransactionEntry.debit(land, Decimal("3000")),
        TransactionEntry.credit(cash, Decimal("3000")))
    led.record_transaction(date(1397, 4, 1), "Earn interest",
        TransactionEntry.debit(cash, Decimal("500")),
        TransactionEntry.credit(revenue, Decimal("500")))
    led.record_transaction(date(1397, 5, 1), "Pay wages",
        TransactionEntry.debit(wages, Decimal("800")),
        TransactionEntry.credit(cash, Decimal("800")))
    return led


# Balance sheet (#67-#72) ---------------------------------------------------

def test_balance_sheet_groups_accounts_by_type():        # #67
    led = _seed_ledger()
    r = led.get_balance_sheet_report()
    assert {row["name"] for row in r["assets"]} == {"Cash", "Land"}
    assert {row["name"] for row in r["liabilities"]} == {"Loans"}
    assert {row["name"] for row in r["equity_accounts"]} == {"Capital"}


def test_balance_sheet_totals_are_accurate():            # #68, #69, #70
    led = _seed_ledger()
    r = led.get_balance_sheet_report()
    # Cash: +10000 +2000 -3000 +500 -800 = 8700; Land: 3000
    assert r["total_assets"] == Decimal("11700.00")
    assert r["total_liabilities"] == Decimal("2000.00")
    # Equity = capital 10000 + net income (500 - 800 = -300) = 9700
    assert r["total_equity_accounts"] == Decimal("10000.00")
    assert r["net_income"] == Decimal("-300.00")
    assert r["total_equity"] == Decimal("9700.00")


def test_balance_sheet_accounting_equation_validates():  # #71, #72
    led = _seed_ledger()
    r = led.get_balance_sheet_report()
    assert r["is_balanced"] is True
    assert r["total_assets"] == r["total_liabilities_and_equity"]


def test_balance_sheet_empty_ledger_is_trivially_balanced():
    led = Ledger("Empty")
    led._silent_mode = True
    r = led.get_balance_sheet_report()
    assert r["total_assets"] == Decimal("0.00")
    assert r["total_liabilities_and_equity"] == Decimal("0.00")
    assert r["is_balanced"] is True


# JSON export (#87-#91) -----------------------------------------------------

def test_json_export_writes_to_nested_data_dir(tmp_path):  # #91
    led = _seed_ledger()
    target = tmp_path / "data" / "exports" / "txns.json"
    n = led.export_transactions_to_json(str(target))
    assert target.exists()
    assert n == 5


def test_json_export_structure_and_content(tmp_path):     # #87, #88, #89, #90
    led = _seed_ledger()
    target = tmp_path / "out.json"
    led.export_transactions_to_json(str(target))
    data = json.loads(target.read_text())
    assert isinstance(data, list) and len(data) == 5      # list of transaction objects
    sample = data[0]
    # Each transaction is a JSON object with the required line items
    assert set(sample.keys()) >= {"id", "date", "description", "debits", "credits"}
    # Account names and account types are both preserved
    assert sample["debits"][0]["account"] == "Cash"
    assert sample["debits"][0]["account_type"] == "ASSET"
    assert sample["credits"][0]["account_type"] == "EQUITY"


# JSON import (#102-#109) ---------------------------------------------------

def test_json_import_roundtrip_preserves_balances(tmp_path):  # #102, #104, #105, #106, #107, #109
    src = _seed_ledger()
    f = tmp_path / "data" / "round.json"
    src.export_transactions_to_json(str(f))

    dst = Ledger("Restored")
    dst._silent_mode = True
    imported = dst.import_transactions_from_json(str(f))

    assert imported == 5
    # Missing accounts were recreated (#106).
    assert dst.get_account("Cash") is not None
    # Account types preserved (#90).
    assert dst.get_account("Capital").type == AccountType.EQUITY
    # Balances match the source ledger.
    assert dst.get_account("Cash").balance == src.get_account("Cash").balance
    assert dst.get_account("Land").balance == src.get_account("Land").balance
    # All imported transactions are balanced (#107).
    assert all(t.is_balanced() for t in dst.transactions)


def test_json_import_summary_is_displayed(tmp_path, capsys):  # acceptance criterion
    led = _seed_ledger()
    f = tmp_path / "summary.json"
    led.export_transactions_to_json(str(f))

    dst = Ledger("Restored")
    # Leave silent_mode off so the summary line prints.
    dst.import_transactions_from_json(str(f))
    out = capsys.readouterr().out
    assert "Import summary" in out
    assert "5 transaction(s) imported" in out


def test_json_import_rejects_unbalanced_records(tmp_path):    # #107
    bad = [{
        "id": "BAD-1",
        "date": "1397-01-01",
        "description": "broken",
        "debits":  [{"account": "Cash",    "account_type": "ASSET",  "amount": "100"}],
        "credits": [{"account": "Capital", "account_type": "EQUITY", "amount": "50"}],
    }]
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(bad))

    led = Ledger("X")
    led._silent_mode = True
    imported = led.import_transactions_from_json(str(f))
    assert imported == 0
    assert led.transactions == []


def test_json_import_verbose_mode_emits_per_transaction(tmp_path, capsys):  # #108
    led = _seed_ledger()
    f = tmp_path / "verbose.json"
    led.export_transactions_to_json(str(f))

    dst = Ledger("Restored")
    dst.import_transactions_from_json(str(f), verbose=True)
    out = capsys.readouterr().out
    # Verbose prints each imported transaction header.
    assert out.count("Transaction") >= 5
