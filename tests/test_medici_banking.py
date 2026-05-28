"""
Tests for medici_banking.AccountType (covers issues #9–#17).

Acceptance criteria mapping:
    - TestAllFiveExist          -> "All five account types exist."
    - TestParsingRejectsUnknown -> "Unsupported account types are rejected."
    - TestNormalBalances        -> "Account types are used consistently
                                    across the ledger."
    - TestLedgerIntegration     -> end-to-end check that the ledger
                                    behaves identically after the refactor.
"""

from datetime import date
from decimal import Decimal

import pytest

from medici_banking import (
    AccountType,
    NormalBalance,
    Account,
    Ledger,
    TransactionEntry,
)


class TestAllFiveExist:
    """Acceptance: all five account types exist."""

    def test_exactly_five_members(self):
        assert len(AccountType) == 5

    def test_expected_members(self):
        assert set(AccountType) == {
            AccountType.ASSET,
            AccountType.LIABILITY,
            AccountType.EQUITY,
            AccountType.REVENUE,
            AccountType.EXPENSE,
        }

    def test_string_values_are_lowercase(self):
        for t in AccountType:
            assert t.value == t.value.lower()


class TestNormalBalances:
    """Acceptance: account types behave consistently across the ledger."""

    @pytest.mark.parametrize(
        "account_type, expected",
        [
            (AccountType.ASSET,     NormalBalance.DEBIT),
            (AccountType.LIABILITY, NormalBalance.CREDIT),
            (AccountType.EQUITY,    NormalBalance.CREDIT),
            (AccountType.REVENUE,   NormalBalance.CREDIT),
            (AccountType.EXPENSE,   NormalBalance.DEBIT),
        ],
    )
    def test_normal_balance(self, account_type, expected):
        assert account_type.normal_balance is expected
        assert account_type.increases_on is expected

    @pytest.mark.parametrize(
        "account_type, expected",
        [
            (AccountType.ASSET,     NormalBalance.CREDIT),
            (AccountType.LIABILITY, NormalBalance.DEBIT),
            (AccountType.EQUITY,    NormalBalance.DEBIT),
            (AccountType.REVENUE,   NormalBalance.DEBIT),
            (AccountType.EXPENSE,   NormalBalance.CREDIT),
        ],
    )
    def test_decreases_on(self, account_type, expected):
        assert account_type.decreases_on is expected

    def test_increases_and_decreases_are_opposites(self):
        for t in AccountType:
            assert t.increases_on is not t.decreases_on


class TestParsingRejectsUnknown:
    """Acceptance: unsupported account types are rejected."""

    @pytest.mark.parametrize("raw", ["asset", "Asset", "ASSET", " asset "])
    def test_parse_value_form(self, raw):
        assert AccountType.parse(raw) is AccountType.ASSET

    @pytest.mark.parametrize("raw", ["LIABILITY", "Liability"])
    def test_parse_name_form_for_json_backwards_compat(self, raw):
        # JSON exports use .name (e.g. "LIABILITY"); parse() must accept that form too.
        assert AccountType.parse(raw) is AccountType.LIABILITY

    def test_parse_passes_enum_through(self):
        assert AccountType.parse(AccountType.REVENUE) is AccountType.REVENUE

    @pytest.mark.parametrize(
        "bad", ["", "income", "loss", "cash", "debit", "credit", "assets"]
    )
    def test_parse_rejects_unknown_strings(self, bad):
        with pytest.raises(ValueError, match="Unsupported account type"):
            AccountType.parse(bad)

    @pytest.mark.parametrize("bad", [None, 123, 1.5, [], {}])
    def test_parse_rejects_non_strings(self, bad):
        with pytest.raises(ValueError, match="must be a string"):
            AccountType.parse(bad)


class TestAccountDebitCredit:
    """Account.debit() and credit() use the enum's normal_balance."""

    @pytest.mark.parametrize(
        "account_type, increases_with_debit",
        [
            (AccountType.ASSET,     True),
            (AccountType.EXPENSE,   True),
            (AccountType.LIABILITY, False),
            (AccountType.EQUITY,    False),
            (AccountType.REVENUE,   False),
        ],
    )
    def test_debit_increases_correct_accounts(self, account_type, increases_with_debit):
        acct = Account("Test", account_type)
        acct.debit(Decimal("100"))
        if increases_with_debit:
            assert acct.balance == Decimal("100")
        else:
            assert acct.balance == Decimal("-100")

    @pytest.mark.parametrize(
        "account_type, increases_with_credit",
        [
            (AccountType.LIABILITY, True),
            (AccountType.EQUITY,    True),
            (AccountType.REVENUE,   True),
            (AccountType.ASSET,     False),
            (AccountType.EXPENSE,   False),
        ],
    )
    def test_credit_increases_correct_accounts(self, account_type, increases_with_credit):
        acct = Account("Test", account_type)
        acct.credit(Decimal("100"))
        if increases_with_credit:
            assert acct.balance == Decimal("100")
        else:
            assert acct.balance == Decimal("-100")


class TestLedgerIntegration:
    """End-to-end: a small ledger produces correct, balanced books."""

    def test_simple_capitalization_and_expense(self):
        ledger = Ledger("Test Bank")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        wages = ledger.create_account("Wages", AccountType.EXPENSE)

        # Initial investment: debit cash, credit capital.
        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry(cash, Decimal("5000")),
            TransactionEntry(capital, Decimal("5000")),
        )

        # Pay wages: debit wages, credit cash (negative on cash).
        ledger.record_transaction(
            date(1397, 2, 1),
            "Wages",
            TransactionEntry(wages, Decimal("300")),
            TransactionEntry(cash, Decimal("-300")),
        )

        assert cash.balance == Decimal("4700")
        assert capital.balance == Decimal("5000")
        assert wages.balance == Decimal("300")

    def test_unbalanced_transaction_rejected(self):
        ledger = Ledger("Test Bank")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)

        with pytest.raises(ValueError, match="not balanced"):
            ledger.record_transaction(
                date(1397, 1, 1),
                "Bad entry",
                TransactionEntry(cash, Decimal("100")),
                TransactionEntry(capital, Decimal("50")),
            )


class TestDocumentation:
    """Each account type has descriptive documentation (issue #16)."""

    def test_all_have_descriptions(self):
        for t in AccountType:
            assert t.description
            assert len(t.description) > 20
