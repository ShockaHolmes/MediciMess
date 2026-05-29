"""Serving layer for Medici historical transaction data.

This script transforms cleaned transactions into analytics-ready tables and
API-ready payloads for the dashboard and reports.

Outputs are written under data/serving/ and include:
- analytics-ready transaction table
- branch summary data
- account summary data
- monthly KPI summary
- alert summary data
- REST API-ready JSON bundles
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_INPUT = DATA_DIR / "medici_transactions_cleaned.csv"
DEFAULT_OUTPUT_DIR = DATA_DIR / "serving"

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

BRANCH_ALIASES = {
    "firenze": "Florence",
    "florence": "Florence",
    "roma": "Rome",
    "rome": "Rome",
    "venice": "Venice",
    "venezia": "Venice",
    "milan": "Milan",
    "milano": "Milan",
    "geneva": "Geneva",
    "geneve": "Geneva",
    "bruges": "Bruges",
    "london": "London",
    "avignon": "Avignon",
    "constance": "Constance",
    "naples": "Naples",
    "pisa": "Pisa",
}

ACCOUNT_ALIASES = {
    "cash": "Cash",
    "deposits payable": "Deposits Payable",
    "loans receivable": "Loans Receivable",
    "loans receivable - government": "Loans Receivable - Government",
    "interest income": "Interest Income",
    "exchange fee revenue": "Exchange Fee Revenue",
    "trading revenue": "Trading Revenue",
    "accounts payable": "Accounts Payable",
    "wages": "Wages",
    "rent": "Rent",
    "supplies": "Supplies",
    "courier services": "Courier Services",
    "security": "Security",
    "maintenance": "Maintenance",
    "political influence expense": "Political Influence Expense",
    "political receivable": "Political Receivable",
    "papal receivable": "Papal Receivable",
    "owner's capital": "Owner's Capital",
    "retained earnings": "Retained Earnings",
}

REVENUE_NAME_HINTS = ("revenue", "income", "fee")
EXPENSE_NAME_HINTS = ("expense", "wages", "rent", "supplies", "courier", "security", "maintenance")
ASSET_NAME_HINTS = ("cash", "receivable", "inventory", "land", "due from")
LIABILITY_NAME_HINTS = ("payable", "loan payable", "deposits payable")
EQUITY_NAME_HINTS = ("capital", "equity", "retained earnings")

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y")
PAGE_SIZE = 100


@dataclass
class ServingStats:
    input_rows: int = 0
    cleaned_rows: int = 0
    duplicate_rows_removed: int = 0
    invalid_rows: int = 0
    alerts_generated: int = 0


@dataclass
class AlertRecord:
    alert_id: int
    rule: str
    severity: str
    branch: str
    period: str
    affected_transaction_ids: list[int]
    counterparty: str
    metric_value: float
    threshold_value: float
    description: str
    detected_at: str
    status: str = "OPEN"


def normalize_space(value: str) -> str:
    return " ".join((value or "").strip().split())


def parse_date(value: str) -> str:
    text = normalize_space(value)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"invalid date: {value!r}")


def standardize_branch(value: str) -> str:
    text = normalize_space(value)
    key = text.casefold()
    if key in BRANCH_ALIASES:
        return BRANCH_ALIASES[key]
    return text.title()


def standardize_account(value: str) -> str:
    text = normalize_space(value)
    if not text:
        return text

    key = text.casefold()
    if key in ACCOUNT_ALIASES:
        return ACCOUNT_ALIASES[key]

    if key.startswith("due from "):
        tail = normalize_space(text[len("due from "):]).title()
        return f"Due from {tail}"

    if key.startswith("loans receivable - "):
        tail = normalize_space(text[len("loans receivable - "):]).title()
        return f"Loans Receivable - {tail}"

    return text.title()


def parse_amount(value: str, field_name: str) -> Decimal:
    text = normalize_space(value)
    try:
        amount = Decimal(text)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{field_name} is not numeric ({value!r})") from exc
    if amount < 0:
        raise ValueError(f"{field_name} must not be negative ({value!r})")
    return amount.quantize(Decimal("0.01"))


def dec_to_float(amount: Decimal) -> float:
    return float(amount.quantize(Decimal("0.01")))


def amount_keys(row: dict[str, str], side: str) -> list[str]:
    prefix = f"{side}_amount"
    keys = [key for key in row if key.startswith(prefix)]
    return sorted(keys, key=lambda key: (len(key), key))


def compute_side_total(row: dict[str, str], side: str) -> Decimal:
    total = Decimal("0")
    for amount_key in amount_keys(row, side):
        suffix = amount_key[len(f"{side}_amount"):]
        account_key = f"{side}_account{suffix}"
        amount_value = normalize_space(row.get(amount_key, ""))
        account_value = normalize_space(row.get(account_key, ""))

        if not amount_value and not account_value:
            continue
        if not amount_value:
            raise ValueError(f"{amount_key} is empty while {account_key} is present")
        if not account_value:
            raise ValueError(f"{account_key} is empty while {amount_key} is present")
        total += parse_amount(amount_value, amount_key)
    return total


def infer_account_type(account_name: str) -> str:
    text = normalize_space(account_name).casefold()
    if not text:
        return "UNKNOWN"
    if any(hint in text for hint in ASSET_NAME_HINTS):
        return "ASSET"
    if any(hint in text for hint in LIABILITY_NAME_HINTS):
        return "LIABILITY"
    if any(hint in text for hint in EQUITY_NAME_HINTS):
        return "EQUITY"
    if any(hint in text for hint in REVENUE_NAME_HINTS):
        return "REVENUE"
    if any(hint in text for hint in EXPENSE_NAME_HINTS):
        return "EXPENSE"
    return "EXPENSE"


def account_normal_balance(account_type: str) -> str:
    return "DEBIT" if account_type in {"ASSET", "EXPENSE"} else "CREDIT"


def transaction_signature(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row.get("date", ""),
        row.get("branch", ""),
        row.get("type", ""),
        row.get("counterparty", ""),
        row.get("debit_account", ""),
        row.get("debit_amount", ""),
        row.get("credit_account", ""),
        row.get("credit_amount", ""),
        row.get("credit_account_2", ""),
        row.get("credit_amount_2", ""),
    )


def period_key(date_value: str) -> str:
    return date_value[:7]


def first_digit(amount: Decimal) -> int | None:
    text = f"{amount.normalize():f}".lstrip("0").lstrip(".")
    for char in text:
        if char.isdigit() and char != "0":
            return int(char)
    return None


def benford_expected() -> dict[int, float]:
    return {digit: math.log10(1 + 1 / digit) for digit in range(1, 10)}


def load_rows(input_path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]], ServingStats]:
    stats = ServingStats()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        source_columns = list(reader.fieldnames or [])

        missing_columns = sorted(REQUIRED_FIELDS - set(source_columns))
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

        cleaned_rows: list[dict[str, str]] = []
        invalid_rows: list[dict[str, Any]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        for row_number, raw_row in enumerate(reader, start=2):
            stats.input_rows += 1
            row = {key: (value if value is not None else "") for key, value in raw_row.items()}

            try:
                normalized = normalize_transaction_row(row, row_number)
                signature = transaction_signature(normalized)
                if signature in seen_signatures:
                    stats.duplicate_rows_removed += 1
                    continue
                seen_signatures.add(signature)
                cleaned_rows.append(normalized)
            except ValueError as exc:
                stats.invalid_rows += 1
                error_row = dict(raw_row)
                error_row["_row_number"] = str(row_number)
                error_row["_error"] = str(exc)
                invalid_rows.append(error_row)

    cleaned_rows.sort(key=lambda row: (row["date"], int(row["id"])))
    stats.cleaned_rows = len(cleaned_rows)
    return cleaned_rows, invalid_rows, stats


def normalize_transaction_row(row: dict[str, str], row_number: int) -> dict[str, str]:
    for field in REQUIRED_FIELDS:
        if not normalize_space(row.get(field, "")):
            raise ValueError(f"missing required field: {field}")

    row["date"] = parse_date(row["date"])
    row["branch"] = standardize_branch(row["branch"])
    row["type"] = normalize_space(row.get("type", ""))
    row["description"] = normalize_space(row.get("description", ""))
    row["counterparty"] = normalize_space(row.get("counterparty", ""))
    row["currency"] = normalize_space(row.get("currency", "florin")) or "florin"

    for key in list(row.keys()):
        if key.startswith("debit_account") or key.startswith("credit_account"):
            row[key] = standardize_account(row.get(key, ""))

    for key in list(row.keys()):
        if key.startswith("debit_amount") or key.startswith("credit_amount"):
            value = normalize_space(row.get(key, ""))
            if value:
                row[key] = f"{parse_amount(value, key):.2f}"

    debit_total = compute_side_total(row, "debit")
    credit_total = compute_side_total(row, "credit")
    if debit_total != credit_total:
        raise ValueError(
            f"unbalanced transaction at row {row_number}: debits={debit_total} credits={credit_total}"
        )

    row["id"] = normalize_space(row["id"])
    row["branch_to"] = normalize_space(row.get("branch_to", ""))
    row["event_name"] = normalize_space(row.get("event_name", ""))
    row["recurrence"] = normalize_space(row.get("recurrence", ""))
    row["trade_good"] = normalize_space(row.get("trade_good", ""))
    return row


def enrich_transactions(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        debit_total = compute_side_total(row, "debit")
        credit_total = compute_side_total(row, "credit")
        row_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        year = row_date.year
        month = row_date.month
        quarter = f"Q{((month - 1) // 3) + 1}"

        debit_type = infer_account_type(row.get("debit_account", ""))
        credit_type = infer_account_type(row.get("credit_account", ""))
        credit2_type = infer_account_type(row.get("credit_account_2", "")) if row.get("credit_account_2") else ""

        transaction_amount = debit_total
        row_amount = dict(row)
        row_amount.update(
            {
                "year": str(year),
                "month": f"{month:02d}",
                "quarter": quarter,
                "period": period_key(row["date"]),
                "transaction_amount": f"{transaction_amount:.2f}",
                "debit_total": f"{debit_total:.2f}",
                "credit_total": f"{credit_total:.2f}",
                "balanced": "yes",
                "debit_account_type": debit_type,
                "credit_account_type": credit_type,
                "credit_account_2_type": credit2_type,
                "normal_balance_debit": account_normal_balance(debit_type),
                "normal_balance_credit": account_normal_balance(credit_type),
            }
        )
        enriched.append(row_amount)
    return enriched


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(data: Any, path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def build_account_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        for side in ("debit", "credit"):
            amount_total = compute_side_total(row, side)
            account_keys = [key for key in row if key.startswith(f"{side}_account")]
            amount_keys_list = amount_keys(row, side)
            for idx, amount_key in enumerate(amount_keys_list):
                suffix = amount_key[len(f"{side}_amount"):]
                account_key = f"{side}_account{suffix}"
                account_name = row.get(account_key, "")
                if not account_name:
                    continue
                amount_raw = row.get(amount_key, "")
                if not amount_raw:
                    continue
                amount = parse_amount(amount_raw, amount_key)
                record = summary.setdefault(
                    account_name,
                    {
                        "account_name": account_name,
                        "account_type": infer_account_type(account_name),
                        "normal_balance": account_normal_balance(infer_account_type(account_name)),
                        "debit_total": Decimal("0"),
                        "credit_total": Decimal("0"),
                        "transaction_count": 0,
                        "first_date": row["date"],
                        "last_date": row["date"],
                    },
                )
                record["transaction_count"] += 1
                if side == "debit":
                    record["debit_total"] += amount
                else:
                    record["credit_total"] += amount
                record["first_date"] = min(record["first_date"], row["date"])
                record["last_date"] = max(record["last_date"], row["date"])

    records: list[dict[str, Any]] = []
    for account_name, record in sorted(summary.items()):
        account_type = record["account_type"]
        if account_type in {"ASSET", "EXPENSE"}:
            ending_balance = record["debit_total"] - record["credit_total"]
        elif account_type in {"LIABILITY", "EQUITY", "REVENUE"}:
            ending_balance = record["credit_total"] - record["debit_total"]
        else:
            ending_balance = record["debit_total"] - record["credit_total"]

        records.append(
            {
                "account_name": account_name,
                "account_type": account_type,
                "normal_balance": record["normal_balance"],
                "debit_total": f"{record['debit_total']:.2f}",
                "credit_total": f"{record['credit_total']:.2f}",
                "ending_balance": f"{ending_balance:.2f}",
                "transaction_count": record["transaction_count"],
                "first_date": record["first_date"],
                "last_date": record["last_date"],
            }
        )
    return records


def build_monthly_kpis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    running_cash: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    running_loans: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for row in rows:
        branch = row["branch"]
        period = row["period"]
        key = (branch, period)
        record = grouped.setdefault(
            key,
            {
                "branch": branch,
                "period": period,
                "transaction_count": 0,
                "cash_inflows": Decimal("0"),
                "cash_outflows": Decimal("0"),
                "deposits": Decimal("0"),
                "withdrawals": Decimal("0"),
                "loans_issued": Decimal("0"),
                "loans_repaid": Decimal("0"),
                "interest_earned": Decimal("0"),
                "operating_expenses": Decimal("0"),
                "trading_revenue": Decimal("0"),
                "exchange_fee_revenue": Decimal("0"),
                "interest_income": Decimal("0"),
                "total_revenue": Decimal("0"),
                "net_income": Decimal("0"),
                "expense_ratio": Decimal("0"),
                "net_cash_movement": Decimal("0"),
                "closing_cash_balance": Decimal("0"),
                "loan_portfolio_balance": Decimal("0"),
            },
        )

        record["transaction_count"] += 1

        debit_amount = compute_side_total(row, "debit")
        credit_amount = compute_side_total(row, "credit")

        if normalize_space(row.get("debit_account", "")).casefold() == "cash":
            record["cash_inflows"] += debit_amount
        if normalize_space(row.get("credit_account", "")).casefold() == "cash":
            record["cash_outflows"] += credit_amount

        tx_type = row.get("type", "").casefold()
        if tx_type == "deposit":
            record["deposits"] += debit_amount
        elif tx_type == "withdrawal":
            record["withdrawals"] += debit_amount
        elif tx_type == "loan_issuance":
            record["loans_issued"] += debit_amount
        elif tx_type == "loan_repayment":
            if normalize_space(row.get("credit_account", "")).casefold() == "loans receivable":
                record["loans_repaid"] += parse_amount(row.get("credit_amount", "0"), "credit_amount")
            if row.get("credit_amount_2") and normalize_space(row.get("credit_account_2", "")).casefold() == "interest income":
                interest = parse_amount(row.get("credit_amount_2", "0"), "credit_amount_2")
                record["interest_earned"] += interest
                record["interest_income"] += interest
        elif tx_type in {"operating_expense", "recurring_operating_expense"}:
            record["operating_expenses"] += debit_amount
        elif tx_type == "trade_transaction":
            record["trading_revenue"] += credit_amount
        elif tx_type == "bill_of_exchange":
            if row.get("credit_amount_2"):
                record["exchange_fee_revenue"] += parse_amount(row.get("credit_amount_2", "0"), "credit_amount_2")
        elif tx_type == "alum_trade":
            record["trading_revenue"] += credit_amount

        # Generic revenue recognition on credit-side accounts.
        if infer_account_type(row.get("credit_account", "")) == "REVENUE":
            record["total_revenue"] += credit_amount
        if row.get("credit_account_2") and infer_account_type(row.get("credit_account_2", "")) == "REVENUE":
            record["total_revenue"] += parse_amount(row.get("credit_amount_2", "0"), "credit_amount_2")

    results: list[dict[str, Any]] = []
    for (branch, period), record in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        record["net_cash_movement"] = record["cash_inflows"] - record["cash_outflows"]
        running_cash[branch] += record["net_cash_movement"]
        running_loans[branch] += record["loans_issued"] - record["loans_repaid"]
        record["closing_cash_balance"] = running_cash[branch]
        record["loan_portfolio_balance"] = running_loans[branch]
        record["net_income"] = record["total_revenue"] - record["operating_expenses"]
        if record["total_revenue"] > 0:
            record["expense_ratio"] = record["operating_expenses"] / record["total_revenue"]

        results.append(
            {
                "branch": branch,
                "period": period,
                "transaction_count": record["transaction_count"],
                "cash_inflows": f"{record['cash_inflows']:.2f}",
                "cash_outflows": f"{record['cash_outflows']:.2f}",
                "net_cash_movement": f"{record['net_cash_movement']:.2f}",
                "closing_cash_balance": f"{record['closing_cash_balance']:.2f}",
                "deposits": f"{record['deposits']:.2f}",
                "withdrawals": f"{record['withdrawals']:.2f}",
                "loans_issued": f"{record['loans_issued']:.2f}",
                "loans_repaid": f"{record['loans_repaid']:.2f}",
                "loan_portfolio_balance": f"{record['loan_portfolio_balance']:.2f}",
                "interest_earned": f"{record['interest_earned']:.2f}",
                "operating_expenses": f"{record['operating_expenses']:.2f}",
                "trading_revenue": f"{record['trading_revenue']:.2f}",
                "exchange_fee_revenue": f"{record['exchange_fee_revenue']:.2f}",
                "interest_income": f"{record['interest_income']:.2f}",
                "total_revenue": f"{record['total_revenue']:.2f}",
                "net_income": f"{record['net_income']:.2f}",
                "expense_ratio": f"{record['expense_ratio']:.4f}",
            }
        )
    return results


def build_branch_summary(monthly_kpis: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_map: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "branch": "",
        "transaction_count": 0,
        "cash_inflows": Decimal("0"),
        "cash_outflows": Decimal("0"),
        "deposits": Decimal("0"),
        "withdrawals": Decimal("0"),
        "loans_issued": Decimal("0"),
        "loans_repaid": Decimal("0"),
        "interest_earned": Decimal("0"),
        "operating_expenses": Decimal("0"),
        "trading_revenue": Decimal("0"),
        "exchange_fee_revenue": Decimal("0"),
        "interest_income": Decimal("0"),
        "total_revenue": Decimal("0"),
        "net_income": Decimal("0"),
        "final_cash_balance": Decimal("0"),
        "loan_portfolio_balance": Decimal("0"),
        "first_date": None,
        "last_date": None,
    })

    for row in rows:
        record = row_map[row["branch"]]
        record["branch"] = row["branch"]
        record["transaction_count"] += 1
        record["first_date"] = row["date"] if record["first_date"] is None else min(record["first_date"], row["date"])
        record["last_date"] = row["date"] if record["last_date"] is None else max(record["last_date"], row["date"])

    for kpi in monthly_kpis:
        record = row_map[kpi["branch"]]
        for key in (
            "cash_inflows",
            "cash_outflows",
            "deposits",
            "withdrawals",
            "loans_issued",
            "loans_repaid",
            "interest_earned",
            "operating_expenses",
            "trading_revenue",
            "exchange_fee_revenue",
            "interest_income",
            "total_revenue",
            "net_income",
        ):
            record[key] += Decimal(kpi[key])
        record["final_cash_balance"] = Decimal(kpi["closing_cash_balance"])
        record["loan_portfolio_balance"] = Decimal(kpi["loan_portfolio_balance"])

    results: list[dict[str, Any]] = []
    for branch, record in sorted(row_map.items()):
        results.append(
            {
                "branch": branch,
                "transaction_count": record["transaction_count"],
                "cash_inflows": f"{record['cash_inflows']:.2f}",
                "cash_outflows": f"{record['cash_outflows']:.2f}",
                "deposits": f"{record['deposits']:.2f}",
                "withdrawals": f"{record['withdrawals']:.2f}",
                "loans_issued": f"{record['loans_issued']:.2f}",
                "loans_repaid": f"{record['loans_repaid']:.2f}",
                "loan_portfolio_balance": f"{record['loan_portfolio_balance']:.2f}",
                "interest_earned": f"{record['interest_earned']:.2f}",
                "operating_expenses": f"{record['operating_expenses']:.2f}",
                "trading_revenue": f"{record['trading_revenue']:.2f}",
                "exchange_fee_revenue": f"{record['exchange_fee_revenue']:.2f}",
                "interest_income": f"{record['interest_income']:.2f}",
                "total_revenue": f"{record['total_revenue']:.2f}",
                "net_income": f"{record['net_income']:.2f}",
                "final_cash_balance": f"{record['final_cash_balance']:.2f}",
                "first_date": record["first_date"],
                "last_date": record["last_date"],
            }
        )
    return results


def build_open_loans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    loans: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("type") not in {"loan_issuance", "loan_repayment"}:
            continue

        key = (row["branch"], row.get("counterparty", ""))
        record = loans.setdefault(
            key,
            {
                "branch": row["branch"],
                "counterparty": row.get("counterparty", ""),
                "first_issued_date": None,
                "last_activity_date": None,
                "total_issued": Decimal("0"),
                "total_repaid": Decimal("0"),
            },
        )
        record["last_activity_date"] = row["date"] if record["last_activity_date"] is None else max(record["last_activity_date"], row["date"])
        if row["type"] == "loan_issuance":
            record["total_issued"] += compute_side_total(row, "debit")
            record["first_issued_date"] = row["date"] if record["first_issued_date"] is None else min(record["first_issued_date"], row["date"])
        else:
            record["total_repaid"] += parse_amount(row.get("credit_amount", "0"), "credit_amount")

    results: list[dict[str, Any]] = []
    for (branch, counterparty), record in sorted(loans.items()):
        outstanding = record["total_issued"] - record["total_repaid"]
        if outstanding <= 0:
            continue
        issue_date = datetime.strptime(record["first_issued_date"], "%Y-%m-%d").date() if record["first_issued_date"] else None
        due_date = (issue_date + timedelta(days=365)).isoformat() if issue_date else ""
        results.append(
            {
                "branch": branch,
                "counterparty": counterparty,
                "first_issued_date": record["first_issued_date"],
                "last_activity_date": record["last_activity_date"],
                "estimated_due_date": due_date,
                "total_issued": f"{record['total_issued']:.2f}",
                "total_repaid": f"{record['total_repaid']:.2f}",
                "outstanding_balance": f"{outstanding:.2f}",
                "status": "OPEN",
            }
        )
    return results


def build_expense_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    breakdown: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "branch": "",
        "debit_account": "",
        "counterparty": "",
        "amount": Decimal("0"),
        "transaction_count": 0,
    })

    for row in rows:
        if row.get("type") not in {"operating_expense", "recurring_operating_expense", "vendor_payment"}:
            continue
        debit_account = row.get("debit_account", "")
        if infer_account_type(debit_account) != "EXPENSE":
            continue
        key = (row["branch"], debit_account, row.get("counterparty", ""))
        record = breakdown[key]
        record["branch"] = row["branch"]
        record["debit_account"] = debit_account
        record["counterparty"] = row.get("counterparty", "")
        record["amount"] += compute_side_total(row, "debit")
        record["transaction_count"] += 1

    results: list[dict[str, Any]] = []
    for key, record in sorted(breakdown.items()):
        results.append(
            {
                "branch": record["branch"],
                "debit_account": record["debit_account"],
                "counterparty": record["counterparty"],
                "amount": f"{record['amount']:.2f}",
                "transaction_count": record["transaction_count"],
            }
        )
    return results


def build_alerts(rows: list[dict[str, Any]]) -> list[AlertRecord]:
    alerts: list[AlertRecord] = []
    alert_id = 1
    detected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Duplicate transaction detection.
    duplicate_groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["branch"],
            row.get("type", ""),
            row.get("counterparty", ""),
            row.get("debit_amount", ""),
            row.get("credit_account", ""),
        )
        duplicate_groups[key].append(row)

    seen_pairs: set[tuple[int, int]] = set()
    for key, group in duplicate_groups.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda row: row["date"])
        for left_index in range(len(ordered) - 1):
            left = ordered[left_index]
            left_date = datetime.strptime(left["date"], "%Y-%m-%d").date()
            for right in ordered[left_index + 1 :]:
                right_date = datetime.strptime(right["date"], "%Y-%m-%d").date()
                if abs((right_date - left_date).days) <= 3:
                    pair = tuple(sorted((int(left["id"]), int(right["id"]))))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    alerts.append(
                        AlertRecord(
                            alert_id=alert_id,
                            rule="C",
                            severity="MEDIUM",
                            branch=key[0],
                            period=left["period"],
                            affected_transaction_ids=[pair[0], pair[1]],
                            counterparty=key[2],
                            metric_value=float(abs((right_date - left_date).days)),
                            threshold_value=3.0,
                            description="Potential duplicate transaction pattern detected within 3 days.",
                            detected_at=detected_at,
                        )
                    )
                    alert_id += 1

    # Vendor concentration and round-number clustering.
    expense_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("type") in {"operating_expense", "recurring_operating_expense", "vendor_payment"}:
            if infer_account_type(row.get("debit_account", "")) == "EXPENSE":
                expense_groups[(row["branch"], row.get("debit_account", ""))].append(row)

    for (branch, debit_account), group in expense_groups.items():
        total = sum((compute_side_total(row, "debit") for row in group), Decimal("0"))
        if total <= 0:
            continue

        by_counterparty: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        ids_by_counterparty: dict[str, list[int]] = defaultdict(list)
        round_number_count = 0
        for row in group:
            amt = compute_side_total(row, "debit")
            counterparty = row.get("counterparty", "")
            by_counterparty[counterparty] += amt
            ids_by_counterparty[counterparty].append(int(row["id"]))
            if (amt * 100).quantize(Decimal("1")) % 5000 == 0:
                round_number_count += 1

        for counterparty, amt in by_counterparty.items():
            share = amt / total
            if share > Decimal("0.05"):
                severity = "HIGH" if share >= Decimal("0.20") else "MEDIUM"
                alerts.append(
                    AlertRecord(
                        alert_id=alert_id,
                        rule="B",
                        severity=severity,
                        branch=branch,
                        period="ALL",
                        affected_transaction_ids=ids_by_counterparty[counterparty],
                        counterparty=counterparty,
                        metric_value=float(share),
                        threshold_value=0.05,
                        description=f"Vendor concentration above 5% for {debit_account}.",
                        detected_at=detected_at,
                    )
                )
                alert_id += 1

        round_share = Decimal(round_number_count) / Decimal(len(group)) if group else Decimal("0")
        if len(group) >= 5 and round_share > Decimal("0.30"):
            alerts.append(
                AlertRecord(
                    alert_id=alert_id,
                    rule="D",
                    severity="MEDIUM",
                    branch=branch,
                    period="ALL",
                    affected_transaction_ids=[int(row["id"]) for row in group],
                    counterparty="",
                    metric_value=float(round_share),
                    threshold_value=0.30,
                    description=f"Round-number clustering detected in {debit_account} expenses.",
                    detected_at=detected_at,
                )
            )
            alert_id += 1

    # Benford deviation by branch + type.
    benford = benford_expected()
    benford_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        amount = parse_amount(row.get("debit_amount", "0"), "debit_amount")
        if amount > 0:
            benford_groups[(row["branch"], row.get("type", ""))].append(row)

    for (branch, tx_type), group in benford_groups.items():
        if len(group) < 10:
            continue
        observed = defaultdict(int)
        ids = []
        for row in group:
            digit = first_digit(parse_amount(row.get("debit_amount", "0"), "debit_amount"))
            if digit is None:
                continue
            observed[digit] += 1
            ids.append(int(row["id"]))
        total = sum(observed.values())
        if total < 10:
            continue
        mad = sum(abs((observed.get(d, 0) / total) - benford[d]) for d in range(1, 10)) / 9
        if mad > 0.015:
            severity = "HIGH" if mad > 0.03 else "MEDIUM"
            alerts.append(
                AlertRecord(
                    alert_id=alert_id,
                    rule="A",
                    severity=severity,
                    branch=branch,
                    period=tx_type,
                    affected_transaction_ids=ids,
                    counterparty="",
                    metric_value=float(mad),
                    threshold_value=0.015,
                    description=f"Benford's Law deviation detected for {tx_type} transactions.",
                    detected_at=detected_at,
                )
            )
            alert_id += 1

    # Transaction frequency outlier by counterparty and type.
    freq_counts: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["branch"], row.get("counterparty", ""), row.get("type", ""), row["period"])
        freq_counts[key].append(row)

    monthly_counts: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    monthly_ids: dict[tuple[str, str, str, str], list[int]] = {}
    for key, group in freq_counts.items():
        branch, counterparty, tx_type, period = key
        monthly_counts[(branch, counterparty, tx_type)].append(len(group))
        monthly_ids[key] = [int(row["id"]) for row in group]

    for (branch, counterparty, tx_type), counts in monthly_counts.items():
        if len(counts) < 3:
            continue
        mean = statistics.mean(counts)
        stdev = statistics.pstdev(counts)
        threshold = mean + (3 * stdev)
        for period in {key[3] for key in monthly_ids if key[0] == branch and key[1] == counterparty and key[2] == tx_type}:
            count = len(freq_counts[(branch, counterparty, tx_type, period)])
            if count > threshold and count >= 3:
                alerts.append(
                    AlertRecord(
                        alert_id=alert_id,
                        rule="E",
                        severity="MEDIUM",
                        branch=branch,
                        period=period,
                        affected_transaction_ids=monthly_ids[(branch, counterparty, tx_type, period)],
                        counterparty=counterparty,
                        metric_value=float(count),
                        threshold_value=float(threshold),
                        description=f"Unusually frequent {tx_type} activity for {counterparty}.",
                        detected_at=detected_at,
                    )
                )
                alert_id += 1

    # Sort by severity then branch then rule for dashboard display.
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda alert: (severity_rank.get(alert.severity, 9), alert.branch, alert.rule, alert.period))
    for idx, alert in enumerate(alerts, start=1):
        alert.alert_id = idx
    return alerts


def build_alert_summary(alerts: list[AlertRecord]) -> list[dict[str, Any]]:
    summary: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "alert_count": 0,
        "affected_transaction_count": 0,
    })
    for alert in alerts:
        key = (alert.rule, alert.severity, alert.branch)
        bucket = summary[key]
        bucket["alert_count"] += 1
        bucket["affected_transaction_count"] += len(alert.affected_transaction_ids)

    rows: list[dict[str, Any]] = []
    for (rule, severity, branch), bucket in sorted(summary.items()):
        rows.append(
            {
                "rule": rule,
                "severity": severity,
                "branch": branch,
                "alert_count": bucket["alert_count"],
                "affected_transaction_count": bucket["affected_transaction_count"],
            }
        )
    return rows


def serialize_alerts(alerts: list[AlertRecord]) -> list[dict[str, Any]]:
    return [
        {
            "alert_id": alert.alert_id,
            "rule": alert.rule,
            "severity": alert.severity,
            "branch": alert.branch,
            "period": alert.period,
            "affected_transaction_ids": alert.affected_transaction_ids,
            "counterparty": alert.counterparty,
            "metric_value": alert.metric_value,
            "threshold_value": alert.threshold_value,
            "description": alert.description,
            "detected_at": alert.detected_at,
            "status": alert.status,
        }
        for alert in alerts
    ]


def build_api_payloads(
    cleaned_rows: list[dict[str, Any]],
    branch_summary: list[dict[str, Any]],
    account_summary: list[dict[str, Any]],
    monthly_kpis: list[dict[str, Any]],
    expense_breakdown: list[dict[str, Any]],
    open_loans: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    total_rows = len(cleaned_rows)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "api_kpis.json": {
            "generated_at": generated_at,
            "branch_summary": branch_summary,
            "monthly_kpi_summary": monthly_kpis,
            "account_summary": account_summary,
        },
        "api_transactions.json": {
            "page": 1,
            "per_page": PAGE_SIZE,
            "total": total_rows,
            "total_pages": max(1, math.ceil(total_rows / PAGE_SIZE)),
            "data": cleaned_rows[:PAGE_SIZE],
        },
        "api_cashflow.json": {
            "generated_at": generated_at,
            "data": [
                {
                    "branch": row["branch"],
                    "period": row["period"],
                    "cash_inflows": row["cash_inflows"],
                    "cash_outflows": row["cash_outflows"],
                    "net_cash_movement": row["net_cash_movement"],
                    "closing_cash_balance": row["closing_cash_balance"],
                }
                for row in monthly_kpis
            ],
        },
        "api_loans.json": {
            "generated_at": generated_at,
            "status": "open",
            "data": open_loans,
        },
        "api_expenses.json": {
            "generated_at": generated_at,
            "data": expense_breakdown,
        },
        "api_alerts.json": {
            "generated_at": generated_at,
            "data": alerts,
        },
    }


def summarize(rows: list[dict[str, Any]], alerts: list[AlertRecord], stats: ServingStats) -> None:
    dates = [row["date"] for row in rows]
    print("=" * 72)
    print("SERVING LAYER SUMMARY")
    print("=" * 72)
    print(f"Input rows scanned:     {stats.input_rows:,}")
    print(f"Cleaned rows written:   {stats.cleaned_rows:,}")
    print(f"Duplicates removed:     {stats.duplicate_rows_removed:,}")
    print(f"Invalid rows removed:   {stats.invalid_rows:,}")
    print(f"Alerts generated:       {len(alerts):,}")
    if dates:
        print(f"Date range:             {min(dates)} to {max(dates)}")
    print("=" * 72)


def transform_serving_layer(input_path: Path, output_dir: Path) -> int:
    cleaned_rows, invalid_rows, stats = load_rows(input_path)
    enriched_rows = enrich_transactions(cleaned_rows)
    monthly_kpis = build_monthly_kpis(enriched_rows)
    branch_summary = build_branch_summary(monthly_kpis, enriched_rows)
    account_summary = build_account_summary(enriched_rows)
    alerts = build_alerts(enriched_rows)
    stats.alerts_generated = len(alerts)
    alert_summary = build_alert_summary(alerts)
    expense_breakdown = build_expense_breakdown(enriched_rows)
    open_loans = build_open_loans(enriched_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    api_dir = output_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    write_csv(enriched_rows, output_dir / "analytics_ready_transactions.csv")
    write_json(enriched_rows, output_dir / "analytics_ready_transactions.json")

    write_csv(branch_summary, output_dir / "branch_summary.csv")
    write_json(branch_summary, output_dir / "branch_summary.json")

    write_csv(account_summary, output_dir / "account_summary.csv")
    write_json(account_summary, output_dir / "account_summary.json")

    write_csv(monthly_kpis, output_dir / "monthly_kpi_summary.csv")
    write_json(monthly_kpis, output_dir / "monthly_kpi_summary.json")

    write_csv(alert_summary, output_dir / "alert_summary.csv")
    write_json(alert_summary, output_dir / "alert_summary.json")

    write_csv(expense_breakdown, output_dir / "expense_breakdown.csv")
    write_json(expense_breakdown, output_dir / "expense_breakdown.json")

    write_csv(open_loans, output_dir / "loan_portfolio.csv")
    write_json(open_loans, output_dir / "loan_portfolio.json")

    write_csv(invalid_rows, output_dir / "invalid_rows.csv")
    write_json(invalid_rows, output_dir / "invalid_rows.json")

    api_payloads = build_api_payloads(
        enriched_rows,
        branch_summary,
        account_summary,
        monthly_kpis,
        expense_breakdown,
        open_loans,
        serialize_alerts(alerts),
    )
    for filename, payload in api_payloads.items():
        write_json(payload, api_dir / filename)

    # Write a compact report manifest for the dashboard and documentation.
    manifest = {
        "source_input": str(input_path),
        "output_dir": str(output_dir),
        "tables": [
            "analytics_ready_transactions",
            "branch_summary",
            "account_summary",
            "monthly_kpi_summary",
            "alert_summary",
            "expense_breakdown",
            "loan_portfolio",
        ],
        "api_payloads": list(api_payloads.keys()),
        "rows_scanned": stats.input_rows,
        "rows_written": stats.cleaned_rows,
        "duplicates_removed": stats.duplicate_rows_removed,
        "invalid_rows": stats.invalid_rows,
        "alerts_generated": len(alerts),
        "date_range": {
            "start": min(row["date"] for row in enriched_rows),
            "end": max(row["date"] for row in enriched_rows),
        },
    }
    write_json(manifest, output_dir / "serving_manifest.json")

    summarize(enriched_rows, alerts, stats)
    print(f"Output directory: {output_dir}")
    print(f"API directory:    {api_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build serving-layer tables and API-ready payloads from cleaned transaction data"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Path to cleaned transaction CSV",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to write serving-layer outputs",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return transform_serving_layer(Path(args.input), Path(args.output_dir))
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
