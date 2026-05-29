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
from pathlib import Path
import sys
import csv
import json

import pytest

# Support running this file directly via: python tests/test_medici_banking.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from medici_banking import (
    AccountType,
    NormalBalance,
    Account,
    Ledger,
    Transaction,
    TransactionEntry,
    UnbalancedTransactionError,
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


class TestTrialBalanceReport:
    """Trial balance report lists all accounts and shows balanced totals."""

    def test_print_trial_balance_lists_accounts_and_totals(self, capsys):
        ledger = Ledger("Trial Balance Demo")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        wages = ledger.create_account("Wages", AccountType.EXPENSE)
        # Keep a zero balance account to ensure all accounts are listed.
        ledger.create_account("Office Supplies", AccountType.ASSET)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("1000")),
            TransactionEntry.credit(capital, Decimal("1000")),
        )

        ledger.record_transaction(
            date(1397, 2, 1),
            "Wages paid",
            TransactionEntry.debit(wages, Decimal("100")),
            TransactionEntry.credit(cash, Decimal("100")),
        )

        ledger.print_trial_balance()
        output = capsys.readouterr().out

        assert "Cash" in output
        assert "Capital" in output
        assert "Wages" in output
        assert "Office Supplies" in output
        assert "TOTAL" in output
        assert "1,000.00" in output
        assert "Ledger balanced: YES" in output

    def test_get_trial_balance_report_returns_structured_data(self):
        ledger = Ledger("Trial Balance Data Demo")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        ledger.create_account("Office Supplies", AccountType.ASSET)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("500.25")),
            TransactionEntry.credit(capital, Decimal("500.25")),
        )

        report = ledger.get_trial_balance_report()

        assert set(report.keys()) == {
            "rows",
            "total_debits",
            "total_credits",
            "is_balanced",
        }
        assert report["total_debits"] == Decimal("500.25")
        assert report["total_credits"] == Decimal("500.25")
        assert report["is_balanced"] is True

        rows_by_name = {row["account_name"]: row for row in report["rows"]}
        assert rows_by_name["Cash"]["account_type"] == "asset"
        assert rows_by_name["Cash"]["debit_balance"] == Decimal("500.25")
        assert rows_by_name["Cash"]["credit_balance"] == Decimal("0.00")
        assert rows_by_name["Office Supplies"]["debit_balance"] == Decimal("0.00")
        assert rows_by_name["Office Supplies"]["credit_balance"] == Decimal("0.00")


class TestIncomeStatementReport:
    """Income statement groups revenue/expenses and computes net income."""

    def test_get_income_statement_report_returns_grouped_data(self):
        ledger = Ledger("Income Statement Data Demo")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        fees = ledger.create_account("Service Fees", AccountType.REVENUE)
        interest = ledger.create_account("Interest Income", AccountType.REVENUE)
        wages = ledger.create_account("Wages", AccountType.EXPENSE)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("1000.00")),
            TransactionEntry.credit(capital, Decimal("1000.00")),
        )

        ledger.record_transaction(
            date(1397, 2, 1),
            "Service income",
            TransactionEntry.debit(cash, Decimal("300.00")),
            TransactionEntry.credit(fees, Decimal("300.00")),
        )

        ledger.record_transaction(
            date(1397, 2, 10),
            "Interest earned",
            TransactionEntry.debit(cash, Decimal("200.00")),
            TransactionEntry.credit(interest, Decimal("200.00")),
        )

        ledger.record_transaction(
            date(1397, 2, 20),
            "Wages paid",
            TransactionEntry.debit(wages, Decimal("150.00")),
            TransactionEntry.credit(cash, Decimal("150.00")),
        )

        report = ledger.get_income_statement_report()

        assert set(report.keys()) == {
            "revenue_accounts",
            "expense_accounts",
            "total_revenue",
            "total_expenses",
            "net_income",
        }
        assert report["total_revenue"] == Decimal("500.00")
        assert report["total_expenses"] == Decimal("150.00")
        assert report["net_income"] == Decimal("350.00")

        revenue_names = {row["account_name"] for row in report["revenue_accounts"]}
        expense_names = {row["account_name"] for row in report["expense_accounts"]}
        assert revenue_names == {"Service Fees", "Interest Income"}
        assert expense_names == {"Wages"}

    def test_print_income_statement_formats_report_output(self, capsys):
        ledger = Ledger("Income Statement Print Demo")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        revenue = ledger.create_account("Consulting Revenue", AccountType.REVENUE)
        expense = ledger.create_account("Office Rent", AccountType.EXPENSE)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("2000.00")),
            TransactionEntry.credit(capital, Decimal("2000.00")),
        )

        ledger.record_transaction(
            date(1397, 1, 15),
            "Consulting services",
            TransactionEntry.debit(cash, Decimal("750.00")),
            TransactionEntry.credit(revenue, Decimal("750.00")),
        )

        ledger.record_transaction(
            date(1397, 1, 20),
            "Rent paid",
            TransactionEntry.debit(expense, Decimal("250.00")),
            TransactionEntry.credit(cash, Decimal("250.00")),
        )

        ledger.print_income_statement()
        output = capsys.readouterr().out

        assert "INCOME STATEMENT" in output
        assert "REVENUE" in output
        assert "EXPENSES" in output
        assert "TOTAL REVENUE" in output
        assert "TOTAL EXPENSES" in output
        assert "NET INCOME" in output
        assert "750.00" in output
        assert "250.00" in output
        assert "500.00" in output


class TestCSVExportFeature:
    """CSV export includes required columns and supports multiple credits."""

    def test_export_transactions_to_csv_writes_line_based_format(self, tmp_path):
        ledger = Ledger("CSV Export Demo")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        receivable = ledger.create_account("Accounts Receivable", AccountType.ASSET)
        interest_income = ledger.create_account("Interest Income", AccountType.REVENUE)

        ledger.record_transaction(
            date(1397, 8, 10),
            "Partial loan repayment with interest",
            TransactionEntry.debit(cash, Decimal("1200.00")),
            TransactionEntry.credit(receivable, Decimal("1000.00")),
            TransactionEntry.credit(interest_income, Decimal("200.00")),
        )

        csv_path = tmp_path / "data" / "transactions.csv"
        exported_count = ledger.export_transactions_to_csv(str(csv_path))

        assert exported_count == 1
        assert csv_path.exists()

        with csv_path.open("r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)

        assert reader.fieldnames == [
            "transaction_id",
            "date",
            "description",
            "line_number",
            "debit_account",
            "debit_amount",
            "credit_account",
            "credit_amount",
        ]
        assert len(rows) == 2

        # First row contains the debit line and first credit line.
        assert rows[0]["transaction_id"] == "1"
        assert rows[0]["date"] == "1397-08-10"
        assert rows[0]["description"] == "Partial loan repayment with interest"
        assert rows[0]["debit_account"] == "Cash"
        assert rows[0]["debit_amount"] == "1200.00"
        assert rows[0]["credit_account"] == "Accounts Receivable"
        assert rows[0]["credit_amount"] == "1000.00"

        # Second row carries the additional credit entry.
        assert rows[1]["transaction_id"] == "1"
        assert rows[1]["line_number"] == "2"
        assert rows[1]["debit_account"] == ""
        assert rows[1]["debit_amount"] == ""
        assert rows[1]["credit_account"] == "Interest Income"
        assert rows[1]["credit_amount"] == "200.00"

    def test_export_transactions_to_csv_defaults_to_data_folder(self, tmp_path, monkeypatch):
        ledger = Ledger("CSV Default Path Demo")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("100.00")),
            TransactionEntry.credit(capital, Decimal("100.00")),
        )

        monkeypatch.chdir(tmp_path)
        ledger.export_transactions_to_csv("phase2_export.csv")

        expected_path = tmp_path / "data" / "phase2_export.csv"
        assert expected_path.exists()


class TestCSVImportFeature:
    """CSV import reloads ledger data, infers types, validates, and tracks counts."""

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        """Helper: write a new-format CSV file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "transaction_id", "date", "description", "line_number",
            "debit_account", "debit_amount", "credit_account", "credit_amount",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def test_round_trip_export_import_reproduces_balances(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ledger = Ledger("Round Trip Bank")
        ledger._silent_mode = True

        cash = ledger.create_account("Cash", AccountType.ASSET)
        receivable = ledger.create_account("Accounts Receivable", AccountType.ASSET)
        interest = ledger.create_account("Interest Income", AccountType.REVENUE)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        wages = ledger.create_account("Wages", AccountType.EXPENSE)

        ledger.record_transaction(
            date(1397, 1, 1), "Founder investment",
            TransactionEntry.debit(cash, Decimal("10000")),
            TransactionEntry.credit(capital, Decimal("10000")),
        )
        ledger.record_transaction(
            date(1397, 8, 10), "Loan repayment with interest",
            TransactionEntry.debit(cash, Decimal("1200")),
            TransactionEntry.credit(receivable, Decimal("1000")),
            TransactionEntry.credit(interest, Decimal("200")),
        )
        ledger.record_transaction(
            date(1397, 12, 1), "Wages paid",
            TransactionEntry.debit(wages, Decimal("300")),
            TransactionEntry.credit(cash, Decimal("300")),
        )

        # Export then import into a fresh ledger.
        ledger.export_transactions_to_csv("export.csv")

        imported = Ledger("Imported Bank")
        imported._silent_mode = True
        count = imported.import_transactions_from_csv("export.csv")

        assert count == 3
        balances = {a.name: a.balance for a in imported.accounts}
        assert balances["Cash"] == Decimal("10900")
        assert balances["Capital"] == Decimal("10000")
        assert balances["Interest Income"] == Decimal("200")
        assert balances["Wages"] == Decimal("300")

    def test_resolves_bare_filename_from_data_folder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        csv_path = tmp_path / "data" / "simple.csv"
        self._write_csv(csv_path, [
            {"transaction_id": "1", "date": "1397-01-01", "description": "Init",
             "line_number": "1", "debit_account": "Cash", "debit_amount": "500",
             "credit_account": "Capital", "credit_amount": "500"},
        ])

        ledger = Ledger("Path Test")
        ledger._silent_mode = True
        count = ledger.import_transactions_from_csv("simple.csv")

        assert count == 1

    def test_infers_account_types_and_auto_creates_accounts(self, tmp_path):
        csv_path = tmp_path / "infer.csv"
        self._write_csv(csv_path, [
            {"transaction_id": "1", "date": "1397-01-01", "description": "Test",
             "line_number": "1", "debit_account": "Cash", "debit_amount": "100",
             "credit_account": "Owner Capital", "credit_amount": "100"},
        ])

        ledger = Ledger("Infer Bank")
        ledger._silent_mode = True
        ledger.import_transactions_from_csv(str(csv_path))

        names = {a.name for a in ledger.accounts}
        assert "Cash" in names
        assert "Owner Capital" in names

        types = {a.name: a.type for a in ledger.accounts}
        assert types["Cash"] == AccountType.ASSET
        assert types["Owner Capital"] == AccountType.EQUITY

    def test_validates_every_transaction_and_skips_invalid(self, tmp_path):
        csv_path = tmp_path / "invalid.csv"
        self._write_csv(csv_path, [
            # Valid transaction
            {"transaction_id": "1", "date": "1397-01-01", "description": "Good",
             "line_number": "1", "debit_account": "Cash", "debit_amount": "200",
             "credit_account": "Capital", "credit_amount": "200"},
            # Unbalanced: 100 debit vs 50 credit
            {"transaction_id": "2", "date": "1397-01-02", "description": "Bad",
             "line_number": "1", "debit_account": "Cash", "debit_amount": "100",
             "credit_account": "Capital", "credit_amount": "50"},
        ])

        ledger = Ledger("Validation Test")
        ledger._silent_mode = True
        count = ledger.import_transactions_from_csv(str(csv_path))

        assert count == 1
        assert len(ledger.transactions) == 1

    def test_tracks_count_of_imported_transactions(self, tmp_path):
        csv_path = tmp_path / "multi.csv"
        rows = []
        for i in range(1, 6):
            rows.append({
                "transaction_id": str(i), "date": f"1397-0{i}-01",
                "description": f"Tx {i}", "line_number": "1",
                "debit_account": "Cash", "debit_amount": "10",
                "credit_account": "Capital", "credit_amount": "10",
            })
        self._write_csv(csv_path, rows)

        ledger = Ledger("Count Test")
        ledger._silent_mode = True
        assert ledger.import_transactions_from_csv(str(csv_path)) == 5

    def test_silent_mode_produces_no_output(self, tmp_path, capsys):
        csv_path = tmp_path / "silent.csv"
        self._write_csv(csv_path, [
            {"transaction_id": "1", "date": "1397-01-01", "description": "Init",
             "line_number": "1", "debit_account": "Cash", "debit_amount": "50",
             "credit_account": "Capital", "credit_amount": "50"},
        ])

        ledger = Ledger("Silent Bank")
        ledger._silent_mode = True
        ledger.import_transactions_from_csv(str(csv_path), verbose=False)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_verbose_mode_prints_transactions_and_summary(self, tmp_path, capsys):
        csv_path = tmp_path / "verbose.csv"
        self._write_csv(csv_path, [
            {"transaction_id": "1", "date": "1397-01-01", "description": "Verbose tx",
             "line_number": "1", "debit_account": "Cash", "debit_amount": "75",
             "credit_account": "Capital", "credit_amount": "75"},
        ])

        ledger = Ledger("Verbose Bank")
        ledger._silent_mode = True
        ledger.import_transactions_from_csv(str(csv_path), verbose=True)

        output = capsys.readouterr().out
        assert "Verbose tx" in output
        assert "Imported 1 transaction" in output


class TestImprovedErrorHandling:
    def test_create_account_rejects_invalid_account_type_with_clear_error(self):
        ledger = Ledger("Type Check")

        with pytest.raises(ValueError, match="Invalid account type"):
            ledger.create_account("Mystery", "not-a-real-type")

    def test_import_csv_missing_file_raises_clear_error(self, tmp_path):
        ledger = Ledger("Missing CSV")
        missing_path = tmp_path / "does_not_exist.csv"

        with pytest.raises(FileNotFoundError, match="CSV import failed: file not found"):
            ledger.import_transactions_from_csv(str(missing_path))

    def test_import_csv_malformed_csv_raises_clear_error(self, tmp_path):
        ledger = Ledger("Malformed CSV")
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text(
            "transaction_id,date,description,debit_account,debit_amount,credit_account,credit_amount\n"
            "1,1397-01-01,Bad line,\"Cash,100,Capital,100\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="Malformed CSV"):
            ledger.import_transactions_from_csv(str(bad_csv))

    def test_import_json_missing_file_raises_clear_error(self, tmp_path):
        ledger = Ledger("Missing JSON")
        missing_path = tmp_path / "does_not_exist.json"

        with pytest.raises(FileNotFoundError, match="JSON import failed: file not found"):
            ledger.import_transactions_from_json(str(missing_path))

    def test_import_json_malformed_json_raises_clear_error(self, tmp_path):
        ledger = Ledger("Malformed JSON")
        bad_json = tmp_path / "bad.json"
        bad_json.write_text('{"id": "TXN-0001"', encoding="utf-8")

        with pytest.raises(ValueError, match="Malformed JSON"):
            ledger.import_transactions_from_json(str(bad_json))


class TestImprovedUserMessages:
    def test_export_methods_print_success_messages_when_not_silent(self, tmp_path, capsys):
        ledger = Ledger("Message Export")
        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("100.00")),
            TransactionEntry.credit(capital, Decimal("100.00")),
        )

        csv_path = tmp_path / "ok.csv"
        json_path = tmp_path / "ok.json"
        ledger.export_transactions_to_csv(str(csv_path))
        ledger.export_transactions_to_json(str(json_path))

        output = capsys.readouterr().out
        assert "Export complete: wrote 1 transaction(s) to CSV" in output
        assert "Export complete: wrote 1 transaction(s) to JSON" in output

    def test_import_json_prints_success_summary_when_not_silent(self, tmp_path, capsys):
        ledger = Ledger("Seed")
        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("50.00")),
            TransactionEntry.credit(capital, Decimal("50.00")),
        )

        json_path = tmp_path / "seed.json"
        ledger.export_transactions_to_json(str(json_path))
        capsys.readouterr()

        imported = Ledger("Import Messages")
        imported.import_transactions_from_json(str(json_path), verbose=False)

        output = capsys.readouterr().out
        assert "Imported 1 transaction(s) from" in output


class TestPhase5CoreAccountingLogic:
    """Explicit requirement coverage for phase-5 core accounting tests."""

    def test_account_debit_behavior(self):
        cash = Account("Cash", AccountType.ASSET)
        cash.debit(Decimal("125.50"))
        assert cash.balance == Decimal("125.50")

    def test_account_credit_behavior(self):
        capital = Account("Capital", AccountType.EQUITY)
        capital.credit(Decimal("125.50"))
        assert capital.balance == Decimal("125.50")

    def test_balanced_transaction_validation(self):
        cash = Account("Cash", AccountType.ASSET)
        capital = Account("Capital", AccountType.EQUITY)
        tx = Transaction(date(1397, 1, 1), "Founder investment")
        tx.add_debit(TransactionEntry.debit(cash, Decimal("500.00")))
        tx.add_credit(TransactionEntry.credit(capital, Decimal("500.00")))

        # Should not raise.
        tx.validate()

    def test_unbalanced_transaction_rejection(self):
        cash = Account("Cash", AccountType.ASSET)
        capital = Account("Capital", AccountType.EQUITY)
        tx = Transaction(date(1397, 1, 1), "Bad posting")
        tx.add_debit(TransactionEntry.debit(cash, Decimal("500.00")))
        tx.add_credit(TransactionEntry.credit(capital, Decimal("300.00")))

        with pytest.raises(UnbalancedTransactionError, match="not balanced"):
            tx.validate()

    def test_ledger_account_creation(self):
        ledger = Ledger("Ledger Account Creation")
        account = ledger.create_account("Cash", AccountType.ASSET)

        assert account.name == "Cash"
        assert account.type == AccountType.ASSET
        assert ledger.get_account("Cash") is account

    def test_transaction_posting(self):
        ledger = Ledger("Transaction Posting")
        ledger._silent_mode = True
        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)

        posted = ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("1000.00")),
            TransactionEntry.credit(capital, Decimal("1000.00")),
        )

        assert posted in ledger.transactions
        assert cash.balance == Decimal("1000.00")
        assert capital.balance == Decimal("1000.00")

    def test_trial_balance_totals(self):
        ledger = Ledger("Trial Balance Totals")
        ledger._silent_mode = True
        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        wages = ledger.create_account("Wages", AccountType.EXPENSE)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("1000.00")),
            TransactionEntry.credit(capital, Decimal("1000.00")),
        )
        ledger.record_transaction(
            date(1397, 1, 15),
            "Wages paid",
            TransactionEntry.debit(wages, Decimal("200.00")),
            TransactionEntry.credit(cash, Decimal("200.00")),
        )

        report = ledger.get_trial_balance_report()
        assert report["total_debits"] == Decimal("1000.00")
        assert report["total_credits"] == Decimal("1000.00")
        assert report["is_balanced"] is True


class TestPhaseImportExportCoverage:
    """Explicit requirement coverage for import/export behavior."""

    def _build_source_ledger(self) -> Ledger:
        ledger = Ledger("Import Export Source")
        ledger._silent_mode = True
        cash = ledger.create_account("Cash", AccountType.ASSET)
        capital = ledger.create_account("Capital", AccountType.EQUITY)
        fees = ledger.create_account("Service Fees", AccountType.REVENUE)

        ledger.record_transaction(
            date(1397, 1, 1),
            "Founder investment",
            TransactionEntry.debit(cash, Decimal("1000.00")),
            TransactionEntry.credit(capital, Decimal("1000.00")),
        )
        ledger.record_transaction(
            date(1397, 1, 10),
            "Service income",
            TransactionEntry.debit(cash, Decimal("250.00")),
            TransactionEntry.credit(fees, Decimal("250.00")),
        )
        return ledger

    def test_phase_csv_export(self, tmp_path):
        ledger = self._build_source_ledger()
        csv_path = tmp_path / "phase_export.csv"

        exported = ledger.export_transactions_to_csv(str(csv_path))

        assert exported == 2
        assert csv_path.exists()

        with csv_path.open("r", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 2
        assert rows[0]["description"] == "Founder investment"
        assert rows[1]["description"] == "Service income"

    def test_phase_json_export(self, tmp_path):
        ledger = self._build_source_ledger()
        json_path = tmp_path / "phase_export.json"

        exported = ledger.export_transactions_to_json(str(json_path))

        assert exported == 2
        assert json_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["description"] == "Founder investment"
        assert data[0]["debits"][0]["account"] == "Cash"
        assert data[0]["credits"][0]["account"] == "Capital"

    def test_phase_csv_import(self, tmp_path):
        source = self._build_source_ledger()
        csv_path = tmp_path / "phase_import.csv"
        source.export_transactions_to_csv(str(csv_path))

        imported = Ledger("Phase CSV Import")
        imported._silent_mode = True
        count = imported.import_transactions_from_csv(str(csv_path))

        assert count == 2
        assert len(imported.transactions) == 2
        balances = {a.name: a.balance for a in imported.accounts}
        assert balances["Cash"] == Decimal("1250.00")
        assert balances["Capital"] == Decimal("1000.00")
        assert balances["Service Fees"] == Decimal("250.00")

    def test_phase_json_import(self, tmp_path):
        source = self._build_source_ledger()
        json_path = tmp_path / "phase_import.json"
        source.export_transactions_to_json(str(json_path))

        imported = Ledger("Phase JSON Import")
        imported._silent_mode = True
        count = imported.import_transactions_from_json(str(json_path))

        assert count == 2
        assert len(imported.transactions) == 2
        balances = {a.name: a.balance for a in imported.accounts}
        assert balances["Cash"] == Decimal("1250.00")
        assert balances["Capital"] == Decimal("1000.00")
        assert balances["Service Fees"] == Decimal("250.00")

    def test_phase_automatic_account_creation(self, tmp_path):
        payload = [
            {
                "id": "TXN-9001",
                "date": "1397-03-01",
                "description": "Auto-create accounts",
                "debits": [
                    {"account": "New Cash Box", "account_type": "ASSET", "amount": "75.00"}
                ],
                "credits": [
                    {"account": "New Owner Capital", "account_type": "EQUITY", "amount": "75.00"}
                ],
            }
        ]
        json_path = tmp_path / "auto_create.json"
        json_path.write_text(json.dumps(payload), encoding="utf-8")

        imported = Ledger("Phase Auto Create")
        imported._silent_mode = True
        count = imported.import_transactions_from_json(str(json_path))

        assert count == 1
        assert imported.get_account("New Cash Box") is not None
        assert imported.get_account("New Owner Capital") is not None

    def test_phase_imported_transaction_balance(self, tmp_path):
        source = self._build_source_ledger()
        json_path = tmp_path / "balanced_check.json"
        source.export_transactions_to_json(str(json_path))

        imported = Ledger("Phase Balanced Check")
        imported._silent_mode = True
        imported.import_transactions_from_json(str(json_path))

        assert imported.transactions
        assert all(tx.is_balanced() for tx in imported.transactions)

    def test_phase_invalid_file_handling(self, tmp_path):
        ledger = Ledger("Phase Invalid File")
        missing_csv = tmp_path / "missing.csv"
        missing_json = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            ledger.import_transactions_from_csv(str(missing_csv))
        with pytest.raises(FileNotFoundError):
            ledger.import_transactions_from_json(str(missing_json))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
