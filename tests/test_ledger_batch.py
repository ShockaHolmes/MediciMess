"""Tests for the Ledger batch (issues #43-#49)."""


from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from medici_banking import (
    Ledger, Account, AccountType, TransactionEntry,
    DuplicateAccountError, DuplicateTransactionError,
)


def _silent_ledger():
    led = Ledger("Test Bank")
    led._silent_mode = True
    return led


# #43 / #44 -----------------------------------------------------------------

def test_ledger_creates_and_stores_accounts():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    assert isinstance(cash, Account)
    assert led.accounts["Cash"] is cash


def test_duplicate_account_rejected():
    led = _silent_ledger()
    led.create_account("Cash", AccountType.ASSET)
    with pytest.raises(DuplicateAccountError):
        led.create_account("Cash", AccountType.ASSET)


# #45 -----------------------------------------------------------------------

def test_find_existing_account():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    assert led.get_account("Cash") is cash
    assert led.get_account("Nope") is None
    assert led.require_account("Cash") is cash
    with pytest.raises(KeyError):
        led.require_account("Nope")


# #46 / #48 -----------------------------------------------------------------

def test_record_valid_transaction_updates_balances():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)

    led.record_transaction(
        date(1397, 1, 1), "Founder investment",
        TransactionEntry.debit(cash, Decimal("5000")),
        TransactionEntry.credit(capital, Decimal("5000")),
    )
    assert cash.balance == Decimal("5000")
    assert capital.balance == Decimal("5000")


def test_unbalanced_transaction_rejected_and_no_side_effects():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)

    with pytest.raises(ValueError, match="not balanced"):
        led.record_transaction(
            date(1397, 1, 1), "Bad entry",
            TransactionEntry.debit(cash, Decimal("100")),
            TransactionEntry.credit(capital, Decimal("50")),
        )
    # Rejected: nothing posted, nothing stored.
    assert cash.balance == Decimal("0")
    assert capital.balance == Decimal("0")
    assert led.transactions == []


# #47 -----------------------------------------------------------------------

def test_posted_transactions_are_stored():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)
    txn = led.record_transaction(
        date(1397, 1, 1), "Investment",
        TransactionEntry.debit(cash, Decimal("100")),
        TransactionEntry.credit(capital, Decimal("100")),
    )
    assert led.transactions == [txn]


# #49 -----------------------------------------------------------------------

def test_auto_ids_are_unique_and_sequential():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)
    t1 = led.record_transaction(date(1397, 1, 1), "a",
                                TransactionEntry.debit(cash, Decimal("1")),
                                TransactionEntry.credit(capital, Decimal("1")))
    t2 = led.record_transaction(date(1397, 1, 2), "b",
                                TransactionEntry.debit(cash, Decimal("1")),
                                TransactionEntry.credit(capital, Decimal("1")))
    assert t1.id == "TXN-0001"
    assert t2.id == "TXN-0002"


def test_duplicate_explicit_id_rejected():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)
    led.record_transaction(date(1397, 1, 1), "a",
                           TransactionEntry.debit(cash, Decimal("1")),
                           TransactionEntry.credit(capital, Decimal("1")),
                           transaction_id="INV-1")
    with pytest.raises(DuplicateTransactionError):
        led.record_transaction(date(1397, 1, 2), "b",
                               TransactionEntry.debit(cash, Decimal("1")),
                               TransactionEntry.credit(capital, Decimal("1")),
                               transaction_id="INV-1")


def test_empty_id_rejected():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)
    with pytest.raises(DuplicateTransactionError):
        led.record_transaction(date(1397, 1, 1), "a",
                               TransactionEntry.debit(cash, Decimal("1")),
                               TransactionEntry.credit(capital, Decimal("1")),
                               transaction_id="   ")


# Trial balance sanity (debits == credits across the ledger) ----------------

def test_trial_balance_is_balanced_after_postings():
    led = _silent_ledger()
    cash = led.create_account("Cash", AccountType.ASSET)
    capital = led.create_account("Capital", AccountType.EQUITY)
    rev = led.create_account("Interest Income", AccountType.REVENUE)
    led.record_transaction(date(1397, 1, 1), "invest",
                           TransactionEntry.debit(cash, Decimal("5000")),
                           TransactionEntry.credit(capital, Decimal("5000")))
    led.record_transaction(date(1397, 6, 1), "interest",
                           TransactionEntry.debit(cash, Decimal("200")),
                           TransactionEntry.credit(rev, Decimal("200")))
    report = led.get_trial_balance_report()
    assert report["is_balanced"] is True
    assert report["total_debits"] == report["total_credits"]
