"""
Medici Banking System - Double-Entry Accounting in Python
 
This implementation showcases the core principles of double-entry accounting, using florins as
 the currency in honor of the Medici banking dynasty. Here's what the code demonstrates:
 
1. **The Fundamental Principle**: Every transaction affects at least two accounts
   (the double-entry principle), and the sum of debits must always equal the sum of credits.
 
2. **Five Main Account Types**:
   - Assets: Resources owned by the business
   - Liabilities: Debts owed by the business
   - Equity: Owner's interest in the business
   - Revenue: Income earned by the business
   - Expenses: Costs incurred by the business
 
3. **Account Balance Rules**:
   - Assets and Expenses: Increased by debits, decreased by credits
   - Liabilities, Equity, and Revenue: Increased by credits, decreased by debits
 
4. **Key Financial Reports**:
   - Trial Balance: Verifies that total debits equal total credits
   - Balance Sheet: Shows Assets = Liabilities + Equity
   - Income Statement: Shows Revenue - Expenses = Net Income
 
The example simulates transactions for the Medici Bank in the year 1397,
including initial capitalization, loans with interest (a key banking activity),
property acquisition, and operating expenses.
"""
 
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from enum import Enum
from typing import Any, List, Tuple, Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path
import csv
import json
 
 
class NormalBalance(str, Enum):
    """The side of a journal entry that increases an account's balance."""
 
    DEBIT = "debit"
    CREDIT = "credit"
 
 
class AccountType(str, Enum):
    """
    The five account types recognized in double-entry bookkeeping.
 
    Inherits from `str` so values serialize cleanly to JSON, slot into Pydantic
    models, and persist as VARCHAR with no custom converters.
 
    Behavior summary (issue #16):
        ASSET     -> normal balance DEBIT  (debits increase, credits decrease)
        LIABILITY -> normal balance CREDIT (credits increase, debits decrease)
        EQUITY    -> normal balance CREDIT (credits increase, debits decrease)
        REVENUE   -> normal balance CREDIT (credits increase, debits decrease)
        EXPENSE   -> normal balance DEBIT  (debits increase, credits decrease)
    """
 
    ASSET = "asset"          # Resources owned by the business that have economic value (e.g. cash, receivables, inventory, land)
    LIABILITY = "liability"  # Debts owed by the business (e.g. payables, loans, customer deposits)
    EQUITY = "equity"        # Owner's interest in the business after liabilities (e.g. capital contributions, retained earnings)
    REVENUE = "revenue"      # Income earned from primary business activities (e.g. interest income, service fees)
    EXPENSE = "expense"      # Costs incurred to generate revenue (e.g. wages, rent, supplies)
 
    @property
    def normal_balance(self) -> NormalBalance:
        """The side that increases this account's balance."""
        return _NORMAL_BALANCES[self]
 
    @property
    def increases_on(self) -> NormalBalance:
        """Alias for `normal_balance`. The side that increases this account."""
        return self.normal_balance
 
    @property
    def decreases_on(self) -> NormalBalance:
        """The side that decreases this account's balance."""
        return (
            NormalBalance.CREDIT
            if self.normal_balance is NormalBalance.DEBIT
            else NormalBalance.DEBIT
        )
 
    @property
    def description(self) -> str:
        """Human-readable description of the account category."""
        return _DESCRIPTIONS[self]
 
    @classmethod
    def parse(cls, value) -> "AccountType":
        """
        Coerce a string (or AccountType) into an AccountType.
 
        Accepts either the value form ("asset") or the member-name form
        ("ASSET"), case-insensitively, with surrounding whitespace tolerated.
        This keeps backward-compat with JSON exports that used `.name`.
 
        Raises:
            ValueError: if `value` does not match a supported account type.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(
                f"Account type must be a string, got {type(value).__name__}"
            )
        cleaned = value.strip()
        # Try the lowercase value form first ("asset")
        try:
            return cls(cleaned.lower())
        except ValueError:
            pass
        # Fall back to uppercase name form ("ASSET") for older JSON files
        try:
            return cls[cleaned.upper()]
        except KeyError:
            pass
        supported = ", ".join(t.value for t in cls)
        raise ValueError(
            f"Unsupported account type: {value!r}. "
            f"Must be one of: {supported}."
        )
 
 
# Behavior tables  ------------------------------------------------
 
_NORMAL_BALANCES: Dict[AccountType, NormalBalance] = {
    AccountType.ASSET:     NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY:    NormalBalance.CREDIT,
    AccountType.REVENUE:   NormalBalance.CREDIT,
    AccountType.EXPENSE:   NormalBalance.DEBIT,
}
 
 
_DESCRIPTIONS: Dict[AccountType, str] = {
    AccountType.ASSET: (
        "Resources owned by the business that have economic value "
        "(e.g. cash, receivables, inventory, land). "
        "Increased by debits, decreased by credits."
    ),
    AccountType.LIABILITY: (
        "Obligations the business owes to others "
        "(e.g. payables, loans, customer deposits). "
        "Increased by credits, decreased by debits."
    ),
    AccountType.EQUITY: (
        "The owners' residual interest in the business after liabilities "
        "(e.g. capital contributions, retained earnings). "
        "Increased by credits, decreased by debits."
    ),
    AccountType.REVENUE: (
        "Income earned from primary business activities "
        "(e.g. interest income, service fees). "
        "Increased by credits, decreased by debits. "
        "Closes into equity at period end."
    ),
    AccountType.EXPENSE: (
        "Costs incurred to generate revenue "
        "(e.g. wages, rent, supplies). "
        "Increased by debits, decreased by credits. "
        "Closes into equity at period end."
    ),
}
class Account:
    """Represents a financial account in the double-entry system"""
 
    def __init__(self, name: str, account_type: AccountType):
        self._name = name
        self._type = account_type
        self._balance = Decimal('0')

    @property
    def name(self) -> str:
        return self._name
 
    @property
    def type(self) -> AccountType:
        return self._type
 
    @property
    def formatted_balance(self) -> str:
        # Storage keeps full precision; only the display is quantized.
        return f"{self._balance:,.2f} florins"
 
    @property
    def balance(self) -> Decimal:
        """Get the current balance of the account"""
        return self._balance
 
    def debit(self, amount: Decimal) -> None:
        """
        Apply a debit to the account
 
        Debits increase ASSET and EXPENSE accounts
        Debits decrease LIABILITY, EQUITY, and REVENUE accounts
        """
        if self.type in (AccountType.ASSET, AccountType.EXPENSE):
            self._balance += amount
        else:
            self._balance -= amount
 
    def credit(self, amount: Decimal) -> None:
        """
        Apply a credit to the account
 
        Credits decrease ASSET and EXPENSE accounts
        Credits increase LIABILITY, EQUITY, and REVENUE accounts
        """
        if self.type in (AccountType.ASSET, AccountType.EXPENSE):
            self._balance -= amount
        else:
            self._balance += amount
 
    def __str__(self) -> str:
        return f"{self.name} ({self.type.name}): {self._balance} florins"
 
    def __repr__(self) -> str:
        return f"Account('{self.name}', {self.type})"
 
 
@dataclass
class TransactionEntry:
    """Represents one debit or credit line in a transaction"""
    account: Account
    amount: Decimal
    is_debit: Optional[bool] = None

    @classmethod
    def debit(cls, account: Account, amount: Decimal) -> "TransactionEntry":
        """Create a debit transaction entry."""
        return cls(account=account, amount=amount, is_debit=True)
 
    @classmethod
    def credit(cls, account: Account, amount: Decimal) -> "TransactionEntry":
        """Create a credit transaction entry."""
        return cls(account=account, amount=amount, is_debit=False)
 
    def __post_init__(self):
        # Normalize and support legacy 2-arg constructor usage by inferring side.
        self.amount = Decimal(str(self.amount))

        if self.amount == 0:
            raise ValueError("Transaction entry amount must not be zero")

        # Backward compatibility: if side is omitted, infer it from account type
        # and amount sign. Positive means normal balance direction, negative means
        # the opposite direction.
        if self.is_debit is None:
            normal_is_debit = self.account.type in (AccountType.ASSET, AccountType.EXPENSE)
            if self.amount > 0:
                self.is_debit = normal_is_debit
            else:
                self.is_debit = not normal_is_debit
            self.amount = abs(self.amount)
        elif self.amount < 0:
            raise ValueError("Transaction entry amount must be greater than zero")
 
    def __str__(self) -> str:
        side = "DEBIT" if self.is_debit else "CREDIT"
        return f"{side} | {self.account.name}: {self.amount} florins"
 
 
class UnbalancedTransactionError(ValueError):
    """Raised when a transaction's debits and credits do not match."""
 
 
@dataclass
class Transaction:
    """Represents a complete financial transaction in the double-entry system"""
    date: date
    description: str
    id: Optional[str] = None                                       # issue #49
    debits: List[TransactionEntry] = field(default_factory=list)   # issue #37
    credits: List[TransactionEntry] = field(default_factory=list)  # issue #38
 
    def add_debit(self, entry: TransactionEntry) -> None:
        """Add a debit entry to the transaction"""
        self.debits.append(entry)
 
    def add_credit(self, entry: TransactionEntry) -> None:
        """Add a credit entry to the transaction"""
        self.credits.append(entry)
 
    def total_debits(self) -> Decimal:
        return sum((e.amount for e in self.debits), Decimal("0"))
 
    def total_credits(self) -> Decimal:
        return sum((e.amount for e in self.credits), Decimal("0"))
 
    def is_balanced(self) -> bool:                       # issue #39
        """Check if the transaction is balanced (debits = credits)"""
        return self.total_debits() == self.total_credits()
 
    def validate(self) -> None:                          # issues #40, #41
        if not self.debits or not self.credits:
            raise UnbalancedTransactionError(
                f"Transaction '{self.description}' on {self.date} needs at "
                f"least one debit and one credit entry."
            )
        td, tc = self.total_debits(), self.total_credits()
        if td != tc:
            raise UnbalancedTransactionError(
                f"Transaction '{self.description}' on {self.date} is not "
                f"balanced: debits total {td}, credits total {tc} "
                f"(off by {abs(td - tc)})."
            )
 
    def post(self) -> None:
        """Post the transaction to update account balances"""
        self.validate()  # Ensure the transaction is valid before posting
        # Apply all debits
        for entry in self.debits:
            entry.account.debit(entry.amount)
        # Apply all credits
        for entry in self.credits:
            entry.account.credit(entry.amount)
 
    def __str__(self) -> str:
        header = f"Transaction: {self.date} - {self.description}"
        if self.id:
            header = f"Transaction {self.id}: {self.date} - {self.description}"
        lines = [header]
 
        lines.append("  Debits:")
        for entry in self.debits:
            lines.append(f"    {entry.account.name}: {entry.amount} florins")
 
        lines.append("  Credits:")
        for entry in self.credits:
            lines.append(f"    {entry.account.name}: {entry.amount} florins")
 
        return '\n'.join(lines)
 
 
class DuplicateAccountError(ValueError):
    """Raised when creating an account name that already exists."""
 
 
class DuplicateTransactionError(ValueError):
    """Raised when a transaction ID is reused, empty, or otherwise invalid."""
 
 
class AccountRegistry(dict[str, Account]):
    """Mapping keyed by account name; iteration yields Account objects."""

    def __iter__(self):
        # Backward compatibility for callers that iterate ledger.accounts
        # and expect Account objects instead of account-name strings.
        return iter(self.values())


class Ledger:
    """The main ledger that keeps track of all accounts and transactions"""
 
    def __init__(self, name: str):
        self.name = name
        self.accounts: AccountRegistry = AccountRegistry()  # issue #44 (keyed by name)
        self.transactions: List[Transaction] = []     # issue #47
        self._used_ids: set[str] = set()              # issue #49
        self._next_seq = 1
        self._silent_mode = False
 
    # --- Account management (#44, #45) ------------------------------------
 
    def create_account(self, name: str, account_type: AccountType | str) -> Account:  # #44
        if name in self.accounts:
            raise DuplicateAccountError(f"Account '{name}' already exists.")
        try:
            parsed_account_type = AccountType.parse(account_type)
        except ValueError as exc:
            supported = ", ".join(t.value for t in AccountType)
            raise ValueError(
                f"Invalid account type for account '{name}': {account_type!r}. "
                f"Supported account types: {supported}."
            ) from exc

        account = Account(name, parsed_account_type)
        self.accounts[name] = account
        return account
 
    def get_account(self, name: str) -> Optional[Account]:                      # #45
        """Find an existing account by name. Returns None if not found."""
        return self.accounts.get(name)
 
    def require_account(self, name: str) -> Account:                            # #45 (strict)
        account = self.accounts.get(name)
        if account is None:
            raise KeyError(f"No account named '{name}' in the ledger.")
        return account
 
    def get_or_create_account(self, name: str, account_type: AccountType) -> Account:
        """Get an existing account by name, or create a new one if absent."""
        existing = self.accounts.get(name)
        if existing is not None:
            return existing
        return self.create_account(name, account_type)
 
    # --- Transaction ID handling (#49) ------------------------------------
 
    def _resolve_id(self, transaction_id: Optional[str]) -> str:
        """
        Return a unique, valid transaction ID, or raise if invalid/duplicate.
 
        - None  -> auto-generate the next free "TXN-NNNN" id.
        - given -> trimmed; rejected if empty or already used.
        """
        if transaction_id is None:
            seq = self._next_seq
            tid = f"TXN-{seq:04d}"
            while tid in self._used_ids:        # skip ids already reserved (e.g. imported)
                seq += 1
                tid = f"TXN-{seq:04d}"
            self._next_seq = seq + 1
            return tid
        tid = str(transaction_id).strip()
        if not tid:
            raise DuplicateTransactionError("Transaction ID cannot be empty or whitespace.")
        if tid in self._used_ids:
            raise DuplicateTransactionError(f"Transaction ID '{tid}' already exists in the ledger.")
        return tid
 
    def record_transaction(self, date: date, description: str,
                           *entries: TransactionEntry,
                           transaction_id: Optional[str] = None) -> Transaction:  # #46
        """
        Records a transaction with any number of debits and credits, ensuring
        debits = credits (the fundamental principle of double-entry).
 
        A transaction is only stored if it has a unique, non-empty ID and it
        balances. A rejected transaction reserves no ID and changes no account.
        """
        transaction = Transaction(date, description)
 
        # Separate entries into debits and credits based on explicit direction.
        for entry in entries:
            if entry.is_debit:
                transaction.add_debit(entry)
            else:
                transaction.add_credit(entry)
 
        # Resolve + validate the ID before anything irreversible happens (#49).
        transaction.id = self._resolve_id(transaction_id)
 
        # Verify the transaction is balanced (#40 / Double-Entry Policy).
        if not transaction.is_balanced():
            debits_total = transaction.total_debits()
            credits_total = transaction.total_credits()
            raise UnbalancedTransactionError(
                f"Transaction is not balanced for '{description}' on {date}: "
                f"debits={debits_total}, credits={credits_total}, "
                f"difference={abs(debits_total - credits_total)}."
            )
 
        # Post to update account balances (#48).
        transaction.post()
 
        # Record the transaction and reserve its ID only after success (#47).
        self.transactions.append(transaction)
        self._used_ids.add(transaction.id)
 
        # Print only if not in silent mode
        if not self._silent_mode:
            print(transaction)
 
        return transaction
 
    # --- Reports ----------------------------------------------------------
 
    def get_trial_balance_report(self) -> Dict[str, Any]:
        """Build a structured trial balance report for UI/API consumers."""
        cent = Decimal("0.01")
        total_debits = Decimal("0")
        total_credits = Decimal("0")
        rows = []
 
        for account in self.accounts.values():
            balance = account.balance
            debit_balance = Decimal("0")
            credit_balance = Decimal("0")
 
            if account.type in (AccountType.ASSET, AccountType.EXPENSE):
                if balance >= 0:
                    debit_balance = balance
                else:
                    credit_balance = abs(balance)
            else:
                if balance >= 0:
                    credit_balance = balance
                else:
                    debit_balance = abs(balance)
 
            total_debits += debit_balance
            total_credits += credit_balance
 
            rows.append(
                {
                    "account_name": account.name,
                    "account_type": account.type.value,
                    "debit_balance": debit_balance.quantize(cent),
                    "credit_balance": credit_balance.quantize(cent),
                }
            )
 
        total_debits = total_debits.quantize(cent)
        total_credits = total_credits.quantize(cent)
 
        return {
            "rows": rows,
            "total_debits": total_debits,
            "total_credits": total_credits,
            "is_balanced": total_debits == total_credits,
        }
 
    def print_trial_balance(self) -> None:
        """Print a trial balance report for all accounts in the ledger."""
        report = self.get_trial_balance_report()
        rows = report["rows"]
        total_debits = report["total_debits"]
        total_credits = report["total_credits"]
        is_balanced = report["is_balanced"]
 
        def _format_amount(value: Decimal) -> str:
            if value == 0:
                return ""
            return f"{value:,.2f}"
 
        print(f"{'Account':<30} {'Type':<12} {'Debit (Florins)':>18} {'Credit (Florins)':>18}")
        print("-" * 82)
 
        for row in rows:
            print(
                f"{row['account_name']:<30} "
                f"{str(row['account_type']).upper():<12} "
                f"{_format_amount(row['debit_balance']):>18} "
                f"{_format_amount(row['credit_balance']):>18}"
            )
 
        print("-" * 82)
        print(
            f"{'TOTAL':<42} "
            f"{total_debits:>18,.2f} "
            f"{total_credits:>18,.2f}"
        )
 
        print(f"\nLedger balanced: {'YES' if is_balanced else 'NO'}")

    def get_balance_sheet_report(self) -> Dict[str, Any]:
        """
        Build a structured balance sheet report (issues #67-#72).
 
        Current-period net income (revenue - expenses) is included as a line
        within equity so the accounting equation validates without requiring
        period-end closing entries. This is standard practice for an interim
        balance sheet.
 
        Returns a dict consumable by both the printer and any future dashboard
        (Dashboard Policy: values come from processed data, not hardcoded).
        """
        cent = Decimal("0.01")
 
        def _section(account_type: AccountType):
            items = []
            total = Decimal("0")
            for account in self.accounts.values():
                if account.type == account_type and account.balance != 0:
                    items.append({"name": account.name,
                                  "amount": account.balance.quantize(cent)})
                    total += account.balance
            return items, total.quantize(cent)
 
        assets, total_assets = _section(AccountType.ASSET)               # #68
        liabilities, total_liabilities = _section(AccountType.LIABILITY) # #69
        equity_accounts, total_equity_accounts = _section(AccountType.EQUITY)  # #70
 
        # Net income from current period revenue and expenses.
        total_revenue = sum(
            (a.balance for a in self.accounts.values() if a.type == AccountType.REVENUE),
            Decimal("0"),
        )
        total_expenses = sum(
            (a.balance for a in self.accounts.values() if a.type == AccountType.EXPENSE),
            Decimal("0"),
        )
        net_income = (total_revenue - total_expenses).quantize(cent)
 
        total_equity = (total_equity_accounts + net_income).quantize(cent)
        total_liab_and_equity = (total_liabilities + total_equity).quantize(cent)
 
        return {
            "assets": assets,
            "total_assets": total_assets,
            "liabilities": liabilities,
            "total_liabilities": total_liabilities,
            "equity_accounts": equity_accounts,
            "total_equity_accounts": total_equity_accounts,
            "net_income": net_income,
            "total_equity": total_equity,
            "total_liabilities_and_equity": total_liab_and_equity,
            "is_balanced": total_assets == total_liab_and_equity,    # #72
        }
    
 
    def print_balance_sheet(self) -> None:
        """Prints a balance sheet (Assets = Liabilities + Equity)"""
        total_assets = Decimal('0')
        total_liabilities = Decimal('0')
        total_equity = Decimal('0')
 
        # Print Assets
        print("ASSETS")
        print("-" * 40)
        for account in self.accounts.values():
            if account.type == AccountType.ASSET and account.balance != 0:
                print(f"{account.name:<30} {account.balance.quantize(Decimal('0.01')):>10}")
                total_assets += account.balance
        print("-" * 40)
        print(f"{'TOTAL ASSETS':<30} {total_assets.quantize(Decimal('0.01')):>10}")
        print()
 
        # Print Liabilities
        print("LIABILITIES")
        print("-" * 40)
        for account in self.accounts.values():
            if account.type == AccountType.LIABILITY and account.balance != 0:
                print(f"{account.name:<30} {account.balance.quantize(Decimal('0.01')):>10}")
                total_liabilities += account.balance
        print("-" * 40)
        print(f"{'TOTAL LIABILITIES':<30} {total_liabilities.quantize(Decimal('0.01')):>10}")
        print()
 
        # Print Equity
        print("EQUITY")
        print("-" * 40)
        for account in self.accounts.values():
            if account.type == AccountType.EQUITY and account.balance != 0:
                print(f"{account.name:<30} {account.balance.quantize(Decimal('0.01')):>10}")
                total_equity += account.balance
        print("-" * 40)
        print(f"{'TOTAL EQUITY':<30} {total_equity.quantize(Decimal('0.01')):>10}")
        print()
 
        # Verify the accounting equation: Assets = Liabilities + Equity
        print("ACCOUNTING EQUATION")
        print("-" * 40)
        print(f"{'Total Assets':<30} {total_assets.quantize(Decimal('0.01')):>10}")
        print(f"{'Total Liabilities + Equity':<30} "
              f"{(total_liabilities + total_equity).quantize(Decimal('0.01')):>10}")
 
        if total_assets == total_liabilities + total_equity:
            print("\nThe accounting equation is balanced! ✓")
        else:
            print("\nWARNING: The accounting equation is NOT balanced! ✗")

    def get_income_statement_report(self) -> Dict[str, Any]:
        """Build a structured income statement report for UI/API consumers."""
        cent = Decimal("0.01")
        revenue_accounts = []
        expense_accounts = []
        total_revenue = Decimal("0")
        total_expenses = Decimal("0")

        for account in self.accounts.values():
            if account.type == AccountType.REVENUE:
                amount = account.balance.quantize(cent)
                revenue_accounts.append(
                    {
                        "account_name": account.name,
                        "amount": amount,
                    }
                )
                total_revenue += amount
            elif account.type == AccountType.EXPENSE:
                amount = account.balance.quantize(cent)
                expense_accounts.append(
                    {
                        "account_name": account.name,
                        "amount": amount,
                    }
                )
                total_expenses += amount

        total_revenue = total_revenue.quantize(cent)
        total_expenses = total_expenses.quantize(cent)
        net_income = (total_revenue - total_expenses).quantize(cent)

        return {
            "revenue_accounts": revenue_accounts,
            "expense_accounts": expense_accounts,
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_income": net_income,
        }

    def print_income_statement(self) -> None:

    

    report = self.get_income_statement_report()
    revenue_accounts = report["revenue_accounts"]
    expense_accounts = report["expense_accounts"]
    total_revenue = report["total_revenue"]
    total_expenses = report["total_expenses"]
    net_income = report["net_income"]

    print("INCOME STATEMENT")
    print("=" * 60)
    print(f"{'Account':<42} {'Amount (Florins)':>18}")
    print("-" * 60)

    print("REVENUE")
    for row in revenue_accounts:
        print(f"{row['account_name']:<42} {row['amount']:>18,.2f}")
    print("-" * 60)
    print(f"{'TOTAL REVENUE':<42} {total_revenue:>18,.2f}")
    print()

    print("EXPENSES")
    for row in expense_accounts:
        print(f"{row['account_name']:<42} {row['amount']:>18,.2f}")
    print("-" * 60)
    print(f"{'TOTAL EXPENSES':<42} {total_expenses:>18,.2f}")
    print()

    net_label = "NET INCOME"
    if net_income < 0:
        net_label = "NET LOSS"
    elif net_income == 0:
        net_label = "BREAK-EVEN"

    print("SUMMARY")
    print("-" * 60)
    print(f"{'TOTAL REVENUE':<42} {total_revenue:>18,.2f}")
    print(f"{'TOTAL EXPENSES':<42} {total_expenses:>18,.2f}")
    print("=" * 60)
    print(f"{net_label:<42} {net_income:>18,.2f}")
 
    def get_kpi_metrics(self,
                        cash_account: str = "Cash",
                        loans_account: str = "Accounts Receivable") -> Dict[str, Any]:
        """
        KPI metrics for the dashboard's headline cards. Values are Decimals;
        the frontend is responsible for currency formatting/serialization.
        """
        bs = self.get_balance_sheet_report()
        cash = self.get_account(cash_account)
        loans = self.get_account(loans_account)
        total_revenue = sum(
            (a.balance for a in self.accounts.values() if a.type == AccountType.REVENUE),
            Decimal("0"),
        )
        total_expenses = sum(
            (a.balance for a in self.accounts.values() if a.type == AccountType.EXPENSE),
            Decimal("0"),
        )
        cent = Decimal("0.01")
        return {
            "total_assets":       bs["total_assets"],
            "total_liabilities":  bs["total_liabilities"],
            "total_equity":       bs["total_equity"],
            "net_income":         bs["net_income"],
            "cash_on_hand":       (cash.balance.quantize(cent) if cash else Decimal("0.00")),
            "loans_outstanding":  (loans.balance.quantize(cent) if loans else Decimal("0.00")),
            "total_revenue":      total_revenue.quantize(cent),
            "total_expenses":     total_expenses.quantize(cent),
            "transaction_count":  len(self.transactions),
            "account_count":      len(self.accounts),
        }
 
    def get_cash_flow_series(self,
                             cash_account: str = "Cash",
                             group_by: str = "month",
                             branch: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Time-series of cash inflows, outflows, and net change for the cash
        flow chart. Periods are grouped by 'month' (YYYY-MM) or 'year' (YYYY).
 
        `branch` filters to a single branch when transactions carry the field;
        comparing branches is done by calling this twice with different values
        and overlaying the two series in the frontend.
 
        Each row: {period, inflow, outflow, net}.
        """
        if group_by not in ("month", "year"):
            raise ValueError("group_by must be 'month' or 'year'")
 
        buckets: Dict[str, Dict[str, Decimal]] = {}
        for txn in self.transactions:
            if branch is not None and txn.branch != branch:
                continue
            key = (txn.date.strftime("%Y-%m") if group_by == "month"
                   else txn.date.strftime("%Y"))
            slot = buckets.setdefault(key, {"inflow": Decimal("0"),
                                            "outflow": Decimal("0")})
            for e in txn.debits:
                if e.account.name == cash_account:
                    slot["inflow"] += e.amount
            for e in txn.credits:
                if e.account.name == cash_account:
                    slot["outflow"] += e.amount
 
        cent = Decimal("0.01")
        rows = []
        for key in sorted(buckets):
            inflow = buckets[key]["inflow"].quantize(cent)
            outflow = buckets[key]["outflow"].quantize(cent)
            rows.append({
                "period":  key,
                "inflow":  inflow,
                "outflow": outflow,
                "net":     (inflow - outflow).quantize(cent),
            })
        return rows
 
    def get_transactions_table(self,
                               limit: Optional[int] = None,
                               search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Structured rows for the dashboard's transaction table. Newest first.
 
        `search` is a case-insensitive substring filter over description,
        transaction id, and account names. `limit` caps the returned rows.
        """
        needle = search.lower() if search else None
        rows: List[Dict[str, Any]] = []
        for txn in reversed(self.transactions):
            debit_names  = [e.account.name for e in txn.debits]
            credit_names = [e.account.name for e in txn.credits]
            if needle is not None:
                haystack = " ".join([
                    txn.description or "",
                    txn.id or "",
                    *debit_names, *credit_names,
                ]).lower()
                if needle not in haystack:
                    continue
            rows.append({
                "id":          txn.id,
                "date":        txn.date.isoformat(),
                "description": txn.description,
                "branch":      txn.branch,
                "amount":      txn.total_debits(),          # debits == credits, either works
                "debit_accounts":  debit_names,
                "credit_accounts": credit_names,
            })
            if limit is not None and len(rows) >= limit:
                break
        return rows
 
    def get_alerts(self,
                   low_cash_threshold: Decimal = Decimal("1000"),
                   cash_account: str = "Cash") -> List[Dict[str, Any]]:
        """
        Rule-based alerts for the alert panel. Each alert carries a `level`
        ('info', 'warning', 'high_risk') so the frontend can separate routine
        warnings from fraud-style indicators. Fraud-detection rules will land
        in a later batch; this version only flags accounting health signals.
        """
        alerts: List[Dict[str, Any]] = []
        bs = self.get_balance_sheet_report()
        if bs["net_income"] < 0:
            alerts.append({
                "level": "warning",
                "source": "income",
                "message": f"Net income is negative ({bs['net_income']} florins).",
            })
        cash = self.get_account(cash_account)
        if cash is not None and cash.balance < low_cash_threshold:
            alerts.append({
                "level": "warning",
                "source": "liquidity",
                "message": (f"Cash on hand ({cash.balance} florins) is below the "
                            f"alert threshold ({low_cash_threshold} florins)."),
            })
        if not bs["is_balanced"]:
            alerts.append({
                "level": "high_risk",
                "source": "integrity",
                "message": "Balance sheet does not satisfy Assets = Liabilities + Equity.",
            })
        return alerts
 
    def get_dashboard_data(self) -> Dict[str, Any]:
        """One-call payload for the dashboard frontend (KPIs, cash flow,
        recent transactions, alerts, and the balance sheet summary)."""
        return {
            "kpis":             self.get_kpi_metrics(),
            "cash_flow":        self.get_cash_flow_series(),
            "recent_transactions": self.get_transactions_table(limit=20),
            "alerts":           self.get_alerts(),
            "balance_sheet":    self.get_balance_sheet_report(),
        }
 
    # --- Pipeline ingestion (data pipeline batch) -------------------------
 
    def ingest_file(self, filename: str, verbose: bool = False) -> int:
        """
        Pipeline ingestion entry point. Dispatches to the right importer by
        file extension (.csv or .json), preserves the raw source file, and
        logs success or failure to the 'medici_banking' logger.
 
        Returns the number of transactions ingested (0 on file-level failure).
        Raw data is never modified; per-record failures are skipped, not
        silently posted (see Data Pipeline Policy).
        """
        ext = os.path.splitext(filename)[1].lower()
        try:
            if ext == ".csv":
                count = self.import_transactions_from_csv(filename, verbose=verbose)
            elif ext == ".json":
                count = self.import_transactions_from_json(filename, verbose=verbose)
            else:
                raise ValueError(f"Unsupported file type for ingestion: {ext!r}. "
                                 f"Expected .csv or .json.")
        except FileNotFoundError:
            logger.error("Ingestion failed: file not found: %s", filename)
            raise
        except (ValueError, json.JSONDecodeError) as e:
            logger.error("Ingestion failed for %s: %s", filename, e)
            raise
        logger.info("Ingested %d transaction(s) from %s", count, filename)
        return count
 
    # --- Import / Export --------------------------------------------------

  
    def export_transactions_to_csv(self, filename: str) -> int:
        """
        Export all transactions to a CSV file.

        CSV column format:
            transaction_id,date,description,line_number,
            debit_account,debit_amount,credit_account,credit_amount

        Each transaction may produce multiple CSV rows to preserve split
        debits/credits. This supports transactions with multiple credit lines.
        
        Args:
            filename: Path to the CSV file to create
            
        Returns:
            Number of transactions exported
        """
        output_path = Path(filename)
        if output_path.parent == Path("."):
            output_path = Path("data") / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'transaction_id',
                'date',
                'description',
                'line_number',
                'debit_account',
                'debit_amount',
                'credit_account',
                'credit_amount',
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for transaction_id, transaction in enumerate(self.transactions, 1):
                row_count = max(len(transaction.debits), len(transaction.credits), 1)
                for line_number in range(1, row_count + 1):
                    debit_entry = (
                        transaction.debits[line_number - 1]
                        if line_number <= len(transaction.debits)
                        else None
                    )
                    credit_entry = (
                        transaction.credits[line_number - 1]
                        if line_number <= len(transaction.credits)
                        else None
                    )

                    writer.writerow(
                        {
                            'transaction_id': transaction_id,
                            'date': transaction.date.isoformat(),
                            'description': transaction.description,
                            'line_number': line_number,
                            'debit_account': debit_entry.account.name if debit_entry else '',
                            'debit_amount': str(debit_entry.amount) if debit_entry else '',
                            'credit_account': credit_entry.account.name if credit_entry else '',
                            'credit_amount': str(credit_entry.amount) if credit_entry else '',
                        }
                    )
        
        exported_count = len(self.transactions)
        if not self._silent_mode:
            print(f"Export complete: wrote {exported_count} transaction(s) to CSV '{output_path}'.")
        return exported_count
 
    def export_transactions_to_json(self, filename: str) -> int:
        """
        Export all transactions to a JSON file.
 
        Returns the number of transactions exported.
        """
        transactions_data = []
 
        for idx, transaction in enumerate(self.transactions, 1):
            trans_dict = {
                'id': transaction.id or f"TXN-{idx:04d}",
                'date': transaction.date.isoformat(),
                'description': transaction.description,
                'debits': [
                    {
                        'account': entry.account.name,
                        'account_type': entry.account.type.name,
                        'amount': str(entry.amount)
                    }
                    for entry in transaction.debits
                ],
                'credits': [
                    {
                        'account': entry.account.name,
                        'account_type': entry.account.type.name,
                        'amount': str(entry.amount)
                    }
                    for entry in transaction.credits
                ]
            }
            transactions_data.append(trans_dict)
 
        output_path = Path(filename)
        if output_path.parent != Path("."):
            output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w', encoding='utf-8') as jsonfile:
            json.dump(transactions_data, jsonfile, indent=2)
 
        exported_count = len(self.transactions)
        if not self._silent_mode:
            print(f"Export complete: wrote {exported_count} transaction(s) to JSON '{output_path}'.")
        return exported_count
 
    def import_transactions_from_csv(self, filename: str, verbose: bool = False) -> int:
        """Import transactions from a CSV file into this ledger.

        Path resolution:
            If ``filename`` contains no directory component, the file is
            resolved relative to the ``data/`` directory of the current
            working directory (mirrors the behaviour of
            :meth:`export_transactions_to_csv`).

        Parsing:
            Supports the current line-based format produced by
            ``export_transactions_to_csv`` (keyed by ``transaction_id``)
            and the older legacy two-credit-column format.

        Account creation:
            Missing accounts are created automatically using
            :meth:`get_or_create_account`.  Account types are inferred from
            account names via :meth:`_infer_account_type`.

        Validation:
            Every reconstructed transaction must balance (total debits ==
            total credits).  Rows that fail validation are skipped; a
            warning is printed when ``verbose=True``.

        Args:
            filename: Path to the CSV file, or a bare filename to be
                resolved inside ``data/``.
            verbose: When ``True``, print each imported transaction and a
                final summary.  When ``False`` (default), produce no
                output.

        Returns:
            Number of transactions successfully imported.
        """
        input_path = Path(filename)
        if input_path.parent == Path("."):
            input_path = Path("data") / input_path

        if not input_path.exists():
            raise FileNotFoundError(
                f"CSV import failed: file not found at '{input_path}'."
            )

        count = 0
        skipped = 0

        try:
            with input_path.open('r', encoding='utf-8', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                if not reader.fieldnames:
                    raise ValueError(
                        f"Malformed CSV in '{input_path}': missing header row."
                    )

                fieldnames = set(reader.fieldnames or [])

                # New CSV format: line-based rows keyed by transaction_id.
                if "transaction_id" in fieldnames:
                    grouped: Dict[str, Dict[str, Any]] = {}
                    order: List[str] = []

                    for row in reader:
                        tx_id = str(row.get("transaction_id", "")).strip()
                        if not tx_id:
                            continue

                        if any(value is None for value in row.values()):
                            raise ValueError(
                                f"Malformed CSV in '{input_path}': row for transaction_id "
                                f"{tx_id!r} has an inconsistent number of columns."
                            )

                        if tx_id not in grouped:
                            grouped[tx_id] = {
                                "date": row.get("date", "").strip(),
                                "description": row.get("description", ""),
                                "debits": [],
                                "credits": [],
                            }
                            order.append(tx_id)

                        debit_account = row.get("debit_account", "").strip()
                        debit_amount_text = row.get("debit_amount", "").strip()
                        if debit_account and debit_amount_text:
                            grouped[tx_id]["debits"].append((debit_account, Decimal(debit_amount_text)))

                        credit_account = row.get("credit_account", "").strip()
                        credit_amount_text = row.get("credit_amount", "").strip()
                        if credit_account and credit_amount_text:
                            grouped[tx_id]["credits"].append((credit_account, Decimal(credit_amount_text)))

                    for tx_id in order:
                        tx_data = grouped[tx_id]
                        try:
                            trans_date = datetime.fromisoformat(tx_data["date"]).date()
                            description = tx_data["description"]

                            transaction = Transaction(trans_date, description)

                            for debit_acc_name, debit_amount in tx_data["debits"]:
                                account_type = self._infer_account_type(debit_acc_name)
                                debit_account = self.get_or_create_account(debit_acc_name, account_type)
                                transaction.add_debit(TransactionEntry.debit(debit_account, debit_amount))

                            for credit_acc_name, credit_amount in tx_data["credits"]:
                                account_type = self._infer_account_type(credit_acc_name)
                                credit_account = self.get_or_create_account(credit_acc_name, account_type)
                                transaction.add_credit(TransactionEntry.credit(credit_account, credit_amount))

                            if not transaction.is_balanced():
                                debit_total = transaction.total_debits()
                                credit_total = transaction.total_credits()
                                raise UnbalancedTransactionError(
                                    f"unbalanced transaction id {tx_id}: "
                                    f"debits={debit_total}, credits={credit_total}"
                                )

                            transaction.post()
                            self.transactions.append(transaction)
                            if verbose:
                                print(transaction)
                            count += 1
                        except (ValueError, KeyError) as e:
                            skipped += 1
                            if verbose:
                                print(f"Warning: Skipping invalid transaction id {tx_id}: {e}")
                            continue

                    if verbose or not self._silent_mode:
                        print(f"Imported {count} transaction(s) from '{input_path}'.")
                        if skipped:
                            print(f"Import summary: {skipped} transaction(s) skipped due to validation errors.")
                    return count

                # Backward-compatible legacy CSV import.
                row_num = 1
                for row in reader:
                    row_num += 1
                    try:
                        trans_date = datetime.fromisoformat(row['date']).date()
                        description = row['description']

                        debit_accounts = [acc.strip() for acc in row.get('debit_account', '').split(',') if acc.strip()]
                        debit_amount = Decimal(row.get('debit_amount', '0'))

                        credit_account = row.get('credit_account', '').strip()
                        credit_amount = Decimal(row.get('credit_amount', '0'))
                        credit_account_2 = row.get('credit_account_2', '').strip()
                        credit_amount_2 = Decimal(row.get('credit_amount_2', '0')) if row.get('credit_amount_2') else Decimal('0')
 
                        transaction = Transaction(trans_date, description)
 
                        # CSV format doesn't track individual debit amounts, so we
                        # distribute the total equally. For precise multi-debit
                        # transactions, use JSON which preserves individual amounts.
                        for debit_acc_name in debit_accounts:
                            account_type = self._infer_account_type(debit_acc_name)
                            debit_account = self.get_or_create_account(debit_acc_name, account_type)
                            transaction.add_debit(TransactionEntry.debit(debit_account, debit_amount / len(debit_accounts)))
 
                        if credit_account:
                            account_type = self._infer_account_type(credit_account)
                            credit_acc = self.get_or_create_account(credit_account, account_type)
                            transaction.add_credit(TransactionEntry.credit(credit_acc, credit_amount))
 
                        if credit_account_2 and credit_amount_2 > 0:
                            account_type = self._infer_account_type(credit_account_2)
                            credit_acc_2 = self.get_or_create_account(credit_account_2, account_type)
                            transaction.add_credit(TransactionEntry.credit(credit_acc_2, credit_amount_2))

                        if not transaction.is_balanced():
                            debit_total = transaction.total_debits()
                            credit_total = transaction.total_credits()
                            raise UnbalancedTransactionError(
                                f"unbalanced transaction at row {row_num}: "
                                f"debits={debit_total}, credits={credit_total}"
                            )

                        transaction.post()
                        self.transactions.append(transaction)
                        if verbose:
                            print(transaction)
                        count += 1

                    except (ValueError, KeyError) as e:
                        skipped += 1
                        if verbose:
                            print(f"Warning: Skipping invalid transaction at row {row_num}: {e}")
                        continue
        except csv.Error as exc:
            raise ValueError(
                f"Malformed CSV in '{input_path}': {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"CSV import failed for '{input_path}': file is not valid UTF-8 text."
            ) from exc

        if verbose or not self._silent_mode:
            print(f"Imported {count} transaction(s) from '{input_path}'.")
            if skipped:
                print(f"Import summary: {skipped} transaction(s) skipped due to validation errors.")
        return count
 
    def import_transactions_from_json(self, filename: str, verbose: bool = False) -> int:
        """
        Import transactions from a JSON file.
 
        Returns the number of transactions imported. Invalid or unbalanced
        records are skipped (and reported when verbose), never silently posted.
        """
        input_path = Path(filename)
        if not input_path.exists():
            raise FileNotFoundError(
                f"JSON import failed: file not found at '{input_path}'."
            )

        count = 0
        skipped = 0

        try:
            with input_path.open('r', encoding='utf-8') as jsonfile:
                transactions_data = json.load(jsonfile)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed JSON in '{input_path}' at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"JSON import failed for '{input_path}': file is not valid UTF-8 text."
            ) from exc

        if not isinstance(transactions_data, list):
            raise ValueError(
                f"Malformed JSON in '{input_path}': expected a top-level list of transactions."
            )
 
        for index, trans_dict in enumerate(transactions_data, start=1):
            try:
                if not isinstance(trans_dict, dict):
                    raise ValueError(
                        f"transaction #{index} must be an object, got {type(trans_dict).__name__}"
                    )

                trans_date = datetime.fromisoformat(trans_dict['date']).date()
                description = trans_dict['description']
 
                transaction = Transaction(trans_date, description)
 
                for debit_entry in trans_dict.get('debits', []):
                    try:
                        account_type = AccountType.parse(debit_entry['account_type'])
                    except ValueError as exc:
                        raise ValueError(
                            f"invalid account type in transaction #{index} debit entry "
                            f"for account '{debit_entry.get('account', '<missing account>')}': "
                            f"{debit_entry.get('account_type')!r}"
                        ) from exc
                    debit_account = self.get_or_create_account(debit_entry['account'], account_type)
                    amount = Decimal(debit_entry['amount'])
                    transaction.add_debit(TransactionEntry.debit(debit_account, amount))
 
                for credit_entry in trans_dict.get('credits', []):
                    try:
                        account_type = AccountType.parse(credit_entry['account_type'])
                    except ValueError as exc:
                        raise ValueError(
                            f"invalid account type in transaction #{index} credit entry "
                            f"for account '{credit_entry.get('account', '<missing account>')}': "
                            f"{credit_entry.get('account_type')!r}"
                        ) from exc
                    credit_account = self.get_or_create_account(credit_entry['account'], account_type)
                    amount = Decimal(credit_entry['amount'])
                    transaction.add_credit(TransactionEntry.credit(credit_account, amount))
 
                # Assign/validate ID (#49) before posting.
                transaction.id = self._resolve_id(trans_dict.get('id') or None)
 
                if not transaction.is_balanced():
                    debit_total = transaction.total_debits()
                    credit_total = transaction.total_credits()
                    raise UnbalancedTransactionError(
                        f"unbalanced transaction #{index}: "
                        f"debits={debit_total}, credits={credit_total}, "
                        f"difference={abs(debit_total - credit_total)}"
                    )
 
                transaction.post()
                self.transactions.append(transaction)
                self._used_ids.add(transaction.id)
 
                if verbose:
                    print(transaction)
 
                count += 1
 
            except (ValueError, KeyError) as e:
                skipped += 1
                if verbose:
                    print(f"Warning: Skipping invalid transaction #{index}: {e}")
                continue

        if verbose or not self._silent_mode:
            print(f"Imported {count} transaction(s) from '{input_path}'.")
            if skipped:
                print(f"Import summary: {skipped} transaction(s) skipped due to validation errors.")
 
        return count
 
    def _infer_account_type(self, account_name: str) -> AccountType:
        """
        Infer the account type from the account name (heuristic for CSV imports
        where the type isn't explicit). Defaults to ASSET when undetermined.
        For precise type control, use JSON import which preserves account types.
        """
        name_lower = account_name.lower()
 
        if any(keyword in name_lower for keyword in ['cash', 'receivable', 'inventory', 'land', 'building', 'equipment', 'asset']):
            return AccountType.ASSET
        if any(keyword in name_lower for keyword in ['payable', 'loan', 'debt', 'liability', 'deposits payable']):
            return AccountType.LIABILITY
        if any(keyword in name_lower for keyword in ['capital', 'equity', 'retained earnings', 'owner']):
            return AccountType.EQUITY
        if any(keyword in name_lower for keyword in ['revenue', 'income', 'sales', 'interest income', 'fee']):
            return AccountType.REVENUE
        if any(keyword in name_lower for keyword in ['expense', 'wages', 'rent', 'supplies', 'maintenance', 'courier', 'cost']):
            return AccountType.EXPENSE
        return AccountType.ASSET
 
 
def main():
    """
    A double-entry accounting system implementation inspired by the
    Florentine banking practices of the Medici family.
    """
    medici_ledger = Ledger("Medici Family Bank")
 
    # Define our chart of accounts
    cash = medici_ledger.create_account("Cash", AccountType.ASSET)
    accounts_receivable = medici_ledger.create_account("Accounts Receivable", AccountType.ASSET)
    inventory = medici_ledger.create_account("Inventory", AccountType.ASSET)
    land = medici_ledger.create_account("Land", AccountType.ASSET)
 
    accounts_payable = medici_ledger.create_account("Accounts Payable", AccountType.LIABILITY)
    loans = medici_ledger.create_account("Loans", AccountType.LIABILITY)
 
    capital = medici_ledger.create_account("Owner's Capital", AccountType.EQUITY)
    retained_earnings = medici_ledger.create_account("Retained Earnings", AccountType.EQUITY)
 
    revenue = medici_ledger.create_account("Revenue", AccountType.REVENUE)
    interest_income = medici_ledger.create_account("Interest Income", AccountType.REVENUE)
 
    expenses = medici_ledger.create_account("Expenses", AccountType.EXPENSE)
    wages = medici_ledger.create_account("Wages", AccountType.EXPENSE)
 
    print("=== 1397 MEDICI BANK SIMULATION ===")
    print("This walkthrough shows how every event records equal debits and credits.\n")
 
    print("[Concept] Owner investment increases assets and owner equity.")
    medici_ledger.record_transaction(
        date(1397, 1, 1),
        "Initial investment from Giovanni de' Medici",
        TransactionEntry.debit(cash, Decimal("10000.00")),
        TransactionEntry.credit(capital, Decimal("10000.00"))
    )
 
    print("\n[Concept] Issuing a loan swaps one asset (cash) for another (receivable).")
    medici_ledger.record_transaction(
        date(1397, 2, 15),
        "Loan to Wool Merchant",
        TransactionEntry.debit(accounts_receivable, Decimal("2000.00")),
        TransactionEntry.credit(cash, Decimal("2000.00"))
    )
 
    print("\n[Concept] Repayments reduce receivables; interest increases revenue.")
    medici_ledger.record_transaction(
        date(1397, 8, 10),
        "Partial loan repayment from Wool Merchant with interest",
        TransactionEntry.debit(cash, Decimal("1200.00")),
        TransactionEntry.credit(accounts_receivable, Decimal("1000.00")),
        TransactionEntry.credit(interest_income, Decimal("200.00"))
    )
 
    print("\n[Concept] Buying long-term assets moves value from cash into land.")
    medici_ledger.record_transaction(
        date(1397, 9, 5),
        "Purchase of land for new Medici banking house",
        TransactionEntry.debit(land, Decimal("3000.00")),
        TransactionEntry.credit(cash, Decimal("3000.00"))
    )
 
    print("\n[Concept] Paying wages records an expense and reduces cash.")
    medici_ledger.record_transaction(
        date(1397, 12, 1),
        "Quarterly wages for bank employees",
        TransactionEntry.debit(wages, Decimal("800.00")),
        TransactionEntry.credit(cash, Decimal("800.00"))
    )
 
    all_balanced = all(transaction.is_balanced() for transaction in medici_ledger.transactions)
    if all_balanced:
        print("\nAll sample transactions are balanced. ✓")
    else:
        print("\nWARNING: At least one sample transaction is unbalanced. ✗")
 
    print("\n=== MEDICI BANK TRIAL BALANCE (Year 1397) ===")
    medici_ledger.print_trial_balance()
 
    print("\n=== MEDICI BANK BALANCE SHEET (Year 1397) ===")
    medici_ledger.print_balance_sheet()
 
    print("\n=== MEDICI BANK INCOME STATEMENT (Year 1397) ===")
    medici_ledger.print_income_statement()
 
 
if __name__ == "__main__":
    main()