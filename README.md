# MediciMess

MediciMess is an educational Python project that simulates Medici Bank-style double-entry bookkeeping in Renaissance Florence and extends it into historical data generation, import/export workflows, branch-operations dashboards, and forensic-analysis exercises.

## Project Overview

The repository is organized around four practical learning goals:

1. Understand how a double-entry ledger works.
2. Generate, validate, import, and export historical banking transactions.
3. Explore analytics and dashboard layouts for branch operations.
4. Practice anomaly detection and fraud-forensics techniques on realistic-looking data.

The codebase is intentionally self-contained and uses only the Python standard library for the core accounting engine and API server.

## Double-Entry Accounting

Double-entry accounting records each transaction with both a debit and a credit. The two sides must balance, which helps preserve the accounting equation and makes posting errors easier to detect.

```text
Assets = Liabilities + Equity
```

In MediciMess, transaction validation, trial balance reports, balance sheet reports, and import checks all rely on that rule.

## Account Types

The ledger uses five account types:

1. Asset: resources owned by the business, such as cash or receivables.
2. Liability: obligations owed to others, such as deposits payable or loans.
3. Equity: the owner's residual interest in the business.
4. Revenue: income earned from operations, such as interest or fees.
5. Expense: costs incurred to run the business.

Assets and expenses normally increase with debits. Liabilities, equity, and revenue normally increase with credits.

## Installation

```bash
git clone https://github.com/ZCW-Spring26/MediciMess.git
cd MediciMess
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

No additional Python packages are required for the core project.

## How to Run

Run the main accounting demo:

```bash
python3 medici-banking.py
```

Alternative module entry point:

```bash
python3 -m medici_banking
```

Run the import/export walkthrough:

```bash
python3 demo_import_export.py
```

Validate the historical transaction dataset:

```bash
python3 validate_transactions.py
```

Generate and expand the historical dataset:

```bash
python3 generate_historical_data.py
python3 generate_additional_data.py
```

Run the analytics scripts:

```bash
python3 benford_analysis.py
python3 vendor_concentration_analysis.py
python3 duplicate_transaction_analysis.py
python3 round_number_clustering_analysis.py
```

Run the full final project demo:

```bash
python3 final_project_demo.py
```

## Usage Examples

Create a ledger, post a balanced transaction, and print a trial balance:

```python
from datetime import date
from decimal import Decimal

from medici_banking import AccountType, Ledger, TransactionEntry

ledger = Ledger("Example Bank")
cash = ledger.create_account("Cash", AccountType.ASSET)
capital = ledger.create_account("Owner's Capital", AccountType.EQUITY)

ledger.record_transaction(
    date(1397, 1, 1),
    "Initial investment",
    TransactionEntry.debit(cash, Decimal("10000.00")),
    TransactionEntry.credit(capital, Decimal("10000.00")),
)

ledger.print_trial_balance()
```

## Import and Export

The project supports both CSV and JSON import/export.

- CSV export writes line-based transaction rows that preserve split debits and credits.
- JSON export preserves the full transaction structure, including account types.
- CSV import automatically creates missing accounts and infers account type from the account name.
- JSON import restores account types directly and is the preferred format for round-tripping.

Typical workflow:

```bash
python3 demo_import_export.py
```

You can also use the API directly:

```python
ledger.export_transactions_to_csv("data/my_export.csv")
ledger.export_transactions_to_json("data/my_export.json")
ledger.import_transactions_from_csv("data/my_export.csv")
ledger.import_transactions_from_json("data/my_export.json")
```

## Historical Dataset

MediciMess includes a historical transaction dataset spanning the 1390–1440 period.

Key files:

- `data/medici_transactions.csv`
- `data/medici_transactions.json`
- `data/medici_transactions_cleaned.csv`
- `data/medici_transactions_expanded.csv`
- `data/serving/` analytics outputs and API-ready JSON bundles

Recommended workflow:

```bash
python3 generate_historical_data.py
python3 generate_additional_data.py
python3 validate_transactions.py
```

The dataset is designed to support large-scale bookkeeping exercises, dashboard analytics, and fraud-detection labs.

## Dashboard Specification Summary

The repository includes a branch-operations dashboard specification for senior bank officials.

The dashboard is intended to show:

- Branch selector and date-range filters.
- KPI cards for cash position, loan portfolio, revenue, expense, net income, overdue loans, and alerts.
- Transaction ledger table with search, sort, and pagination.
- Cash flow charts with branch comparison.
- Anomaly and alert panels for duplicate transactions, vendor concentration, Benford deviation, and round-number clustering.
- Role-based access control and audit-friendly reporting.

Current wireframe pages:

- `branch_operations_dashboard.html`
- `transaction_ledger_view.html`

To view them locally:

```bash
python3 -m http.server 5500
```

Then open:

- `http://127.0.0.1:5500/branch_operations_dashboard.html`
- `http://127.0.0.1:5500/transaction_ledger_view.html`

## Forensic Analysis Summary

MediciMess also includes a forensic-analysis scenario built around a hidden embezzlement trail in the Florence branch expense data.

The analysis exercises focus on:

- Benford's Law deviation.
- Vendor concentration.
- Duplicate transaction detection.
- Round-number clustering.

Useful scripts:

- `benford_analysis.py`
- `vendor_concentration_analysis.py`
- `duplicate_transaction_analysis.py`
- `round_number_clustering_analysis.py`

The outputs are written to `data/serving/` and can be exposed through the serving-layer API for dashboard consumption.

## Backend API and Serving Layer

The serving-layer API reads precomputed analytics from `data/serving/` and exposes endpoints for the dashboard and related reports.

Helpful commands:

```bash
make serve-data
make run-api
make final-demo
```

Common endpoints include:

- `/api/kpis`
- `/api/transactions`
- `/api/cashflow`
- `/api/loans`
- `/api/expenses`
- `/api/alerts`

## Project Structure

- `src/` contains the reusable accounting package.
- `data/` stores source, transformed, and serving datasets.
- `docs/` contains specifications and supporting guidance.
- `tests/` contains unit tests for accounting and data workflows.
- `reports/` stores generated outputs for exercises and analysis.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.

Copyright (c) 2025 Zip Code Wilmington Core
