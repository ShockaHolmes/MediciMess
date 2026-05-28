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
        # Ensure amount is a Decimal
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


@dataclass
class Transaction:
    """Represents a complete financial transaction in the double-entry system"""
    date: date
    description: str
    debits: List[TransactionEntry] = field(default_factory=list)
    credits: List[TransactionEntry] = field(default_factory=list)
    
    def add_debit(self, entry: TransactionEntry) -> None:
        """Add a debit entry to the transaction"""
        self.debits.append(entry)
    
    def add_credit(self, entry: TransactionEntry) -> None:
        """Add a credit entry to the transaction"""
        self.credits.append(entry)
    
    def is_balanced(self) -> bool:
        """Check if the transaction is balanced (debits = credits)"""
        total_debits = sum(entry.amount for entry in self.debits)
        total_credits = sum(entry.amount for entry in self.credits)
        return total_debits == total_credits
    
    def post(self) -> None:
        """Post the transaction to update account balances"""
        # Apply all debits
        for entry in self.debits:
            entry.account.debit(entry.amount)
        
        # Apply all credits
        for entry in self.credits:
            entry.account.credit(entry.amount)
    
    def __str__(self) -> str:
        lines = [f"Transaction: {self.date} - {self.description}"]
        
        lines.append("  Debits:")
        for entry in self.debits:
            lines.append(f"    {entry.account.name}: {entry.amount} florins")
        
        lines.append("  Credits:")
        for entry in self.credits:
            lines.append(f"    {entry.account.name}: {entry.amount} florins")
        
        return '\n'.join(lines)


class Ledger:
    """The main ledger that keeps track of all accounts and transactions"""
    
    def __init__(self, name: str):
        self.name = name
        self.accounts: List[Account] = []
        self.transactions: List[Transaction] = []
        self._silent_mode = False  # Flag for suppressing transaction output
    
    def create_account(self, name: str, account_type: AccountType) -> Account:
        """Create a new account and add it to the ledger"""
        account = Account(name, account_type)
        self.accounts.append(account)
        return account
    
    def get_or_create_account(self, name: str, account_type: AccountType) -> Account:
        """Get an existing account by name or create a new one if it doesn't exist"""
        for account in self.accounts:
            if account.name == name:
                return account
        return self.create_account(name, account_type)
    
    def record_transaction(self, date: date, description: str, 
                          *entries: TransactionEntry) -> None:
        """
        Records a transaction with any number of debits and credits,
        ensuring that debits = credits (the fundamental principle of double-entry)
        """
        transaction = Transaction(date, description)
        
        # Separate entries into debits and credits based on explicit entry direction.
        for entry in entries:
            if entry.is_debit:
                transaction.add_debit(entry)
            else:
                transaction.add_credit(entry)
        
        # Verify that the transaction is balanced
        if not transaction.is_balanced():
            raise ValueError("Transaction is not balanced: debits must equal credits")
        
        # Post the transaction to update account balances
        transaction.post()
        
        # Record the transaction in the ledger
        self.transactions.append(transaction)
        
        # Print only if not in silent mode
        if not self._silent_mode:
            print(transaction)

    def get_trial_balance_report(self) -> Dict[str, Any]:
        """Build a structured trial balance report for UI/API consumers."""
        cent = Decimal("0.01")
        total_debits = Decimal("0")
        total_credits = Decimal("0")
        rows = []

        for account in self.accounts:
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
    
    def print_balance_sheet(self) -> None:
        """Prints a balance sheet (Assets = Liabilities + Equity)"""
        total_assets = Decimal('0')
        total_liabilities = Decimal('0')
        total_equity = Decimal('0')
        
        # Print Assets
        print("ASSETS")
        print("-" * 40)
        for account in self.accounts:
            if account.type == AccountType.ASSET and account.balance != 0:
                print(f"{account.name:<30} {account.balance.quantize(Decimal('0.01')):>10}")
                total_assets += account.balance
        print("-" * 40)
        print(f"{'TOTAL ASSETS':<30} {total_assets.quantize(Decimal('0.01')):>10}")
        print()
        
        # Print Liabilities
        print("LIABILITIES")
        print("-" * 40)
        for account in self.accounts:
            if account.type == AccountType.LIABILITY and account.balance != 0:
                print(f"{account.name:<30} {account.balance.quantize(Decimal('0.01')):>10}")
                total_liabilities += account.balance
        print("-" * 40)
        print(f"{'TOTAL LIABILITIES':<30} {total_liabilities.quantize(Decimal('0.01')):>10}")
        print()
        
        # Print Equity
        print("EQUITY")
        print("-" * 40)
        for account in self.accounts:
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

        for account in self.accounts:
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
        """Print an income statement grouped by revenue and expense accounts."""
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
        
        return len(self.transactions)
    
    def export_transactions_to_json(self, filename: str) -> int:
        """
        Export all transactions to a JSON file
        
        Args:
            filename: Path to the JSON file to create
            
        Returns:
            Number of transactions exported
        """
        transactions_data = []
        
        for idx, transaction in enumerate(self.transactions, 1):
            trans_dict = {
                'id': idx,
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
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(transactions_data, jsonfile, indent=2)
        
        return len(self.transactions)
    
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

        count = 0
        skipped = 0

        with open(input_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = set(reader.fieldnames or [])

            # New CSV format: line-based rows keyed by transaction_id.
            if "transaction_id" in fieldnames:
                grouped: Dict[str, Dict[str, Any]] = {}
                order: List[str] = []

                for row in reader:
                    tx_id = str(row.get("transaction_id", "")).strip()
                    if not tx_id:
                        continue

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
                            raise ValueError("Transaction is not balanced: debits must equal credits")

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

                if verbose:
                    print(f"\nImported {count} transaction(s) from '{input_path}'."
                          + (f"  {skipped} skipped." if skipped else ""))
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
                        raise ValueError("Transaction is not balanced: debits must equal credits")

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

        if verbose:
            print(f"\nImported {count} transaction(s) from '{input_path}'."
                  + (f"  {skipped} skipped." if skipped else ""))
        return count
    
    def import_transactions_from_json(self, filename: str, verbose: bool = False) -> int:
        """
        Import transactions from a JSON file
        
        Args:
            filename: Path to the JSON file to import
            verbose: If True, print each transaction as it's imported
            
        Returns:
            Number of transactions imported
        """
        count = 0
        
        with open(filename, 'r', encoding='utf-8') as jsonfile:
            transactions_data = json.load(jsonfile)
        
        for trans_dict in transactions_data:
            try:
                # Parse the transaction
                trans_date = datetime.fromisoformat(trans_dict['date']).date()
                description = trans_dict['description']
                
                # Create the transaction directly
                transaction = Transaction(trans_date, description)
                
                # Add debit entries
                for debit_entry in trans_dict.get('debits', []):
                    account_type = AccountType[debit_entry['account_type']]
                    debit_account = self.get_or_create_account(debit_entry['account'], account_type)
                    amount = Decimal(debit_entry['amount'])
                    transaction.add_debit(TransactionEntry.debit(debit_account, amount))
                
                # Add credit entries
                for credit_entry in trans_dict.get('credits', []):
                    account_type = AccountType[credit_entry['account_type']]
                    credit_account = self.get_or_create_account(credit_entry['account'], account_type)
                    amount = Decimal(credit_entry['amount'])
                    transaction.add_credit(TransactionEntry.credit(credit_account, amount))
                
                # Verify that the transaction is balanced
                if not transaction.is_balanced():
                    raise ValueError("Transaction is not balanced: debits must equal credits")
                
                # Post the transaction to update account balances
                transaction.post()
                
                # Record the transaction in the ledger
                self.transactions.append(transaction)
                
                # Print if verbose
                if verbose:
                    print(transaction)
                
                count += 1
                
            except (ValueError, KeyError) as e:
                if verbose:
                    print(f"Warning: Skipping invalid transaction: {e}")
                continue
        
        return count
    
    def _infer_account_type(self, account_name: str) -> AccountType:
        """
        Infer the account type from the account name
        This is a heuristic-based approach for CSV imports where type isn't explicit.
        
        Note: Defaults to ASSET if account type cannot be determined. This is a safe
        default for unknown accounts as most banking transactions involve asset accounts.
        For precise type control, use JSON import which preserves account types.
        """
        name_lower = account_name.lower()
        
        # Asset accounts
        if any(keyword in name_lower for keyword in ['cash', 'receivable', 'inventory', 'land', 'building', 'equipment', 'asset']):
            return AccountType.ASSET
        
        # Liability accounts
        if any(keyword in name_lower for keyword in ['payable', 'loan', 'debt', 'liability', 'deposits payable']):
            return AccountType.LIABILITY
        
        # Equity accounts
        if any(keyword in name_lower for keyword in ['capital', 'equity', 'retained earnings', 'owner']):
            return AccountType.EQUITY
        
        # Revenue accounts
        if any(keyword in name_lower for keyword in ['revenue', 'income', 'sales', 'interest income', 'fee']):
            return AccountType.REVENUE
        
        # Expense accounts
        if any(keyword in name_lower for keyword in ['expense', 'wages', 'rent', 'supplies', 'maintenance', 'courier', 'cost']):
            return AccountType.EXPENSE
        
        # Default to ASSET if we can't determine
        return AccountType.ASSET


def main():
    """
    A double-entry accounting system implementation inspired by the
    Florentine banking practices of the Medici family.
    """
    # Create a new ledger for our banking operations
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
    
    # Running a full year simulation with concept-driven narration.
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
    
    # Print the trial balance to verify our accounting is balanced
    print("\n=== MEDICI BANK TRIAL BALANCE (Year 1397) ===")
    medici_ledger.print_trial_balance()
    
    # Print the balance sheet
    print("\n=== MEDICI BANK BALANCE SHEET (Year 1397) ===")
    medici_ledger.print_balance_sheet()
    
    # Print the income statement
    print("\n=== MEDICI BANK INCOME STATEMENT (Year 1397) ===")
    medici_ledger.print_income_statement()


if __name__ == "__main__":
    main()
