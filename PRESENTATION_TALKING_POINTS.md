# MediciMess - Presentation Talking Points

## 30-Second Project Summary

MediciMess is a Python project that simulates a Medici Bank-style double-entry ledger and turns it into a full accounting and analytics workflow. It includes transaction posting, trial balance and financial statement reporting, CSV/JSON import-export, a historical transaction dataset, and a forensic analysis layer that looks for suspicious vendor behavior and other anomalies.

## 90-Second Project Summary

MediciMess started as a double-entry accounting engine, then grew into a complete educational finance and data pipeline project. The core ledger models assets, liabilities, equity, revenue, and expenses, and enforces balanced transactions so every debit has a matching credit. On top of that, I added reporting for trial balance, balance sheet, and income statement, plus import/export support so the ledger can round-trip through CSV and JSON.

The project also includes a historical Medici Bank dataset with tens of thousands of simulated transactions, a serving layer that exposes cleaned analytics, and a browser-based dashboard for cash flow, KPIs, and alerts. For the forensic side, I built scripts that detect vendor concentration, duplicate activity, Benford-style deviations, and round-number clustering to help surface suspicious behavior. Overall, it combines accounting logic, data engineering, analytics, and fraud detection in one portfolio project.

## Technical Skills Used

- Python, object-oriented design, and dataclasses
- Double-entry accounting logic and financial reporting
- CSV and JSON parsing, validation, and export
- Decimal-based money handling for financial accuracy
- Data generation, cleanup, and transformation pipelines
- REST-style API serving for dashboard consumption
- Static HTML, CSS, and JavaScript for dashboard presentation
- Automated testing with pytest
- Anomaly detection and statistical analysis

## Data Engineering Value

- Converts raw ledger-style records into analytics-ready outputs
- Demonstrates import, transform, serve, and validate workflow patterns
- Produces reusable CSV and JSON artifacts for downstream reporting
- Shows how financial source data can feed dashboards and alerts
- Reinforces data quality checks, schema validation, and reproducibility

## Accounting and Business Value

- Models the core rules of double-entry bookkeeping
- Validates that transactions stay balanced before they affect the ledger
- Produces standard financial statements used in real accounting workflows
- Supports transaction history review, export, and audit-style analysis
- Demonstrates how business records can be organized for reporting and control

## Forensic Analysis Feature

The forensic analysis layer scans the historical dataset for suspicious patterns that may indicate fraud or misuse. It checks for vendor concentration, duplicate or near-duplicate transactions, Benford-style digit anomalies, and round-number clustering. That makes the project useful not just for accounting practice, but also for teaching how investigators look for irregularities in financial data.

## What Could Be Added Next

- A web UI with filters, drill-downs, and alert triage
- More realistic role-based access control and audit logs
- Additional anomaly rules for timing, frequency, and network analysis
- Database storage instead of file-based persistence
- Scenario-based regression tests for fraud investigations
- A packaged CLI so the demo can run as a single command everywhere

## One-Line Elevator Pitch

MediciMess is a Python accounting and fraud-detection project that combines double-entry bookkeeping, historical transaction data, and anomaly analysis into a portfolio-ready finance platform.

## GitHub README About Section

```markdown
## About

MediciMess is a Python project that simulates Medici Bank-style double-entry bookkeeping and expands it into a full accounting, analytics, and forensic investigation workflow.

The project includes:

- A core ledger with balanced transaction posting
- Trial balance, balance sheet, and income statement reporting
- CSV and JSON import/export for transaction data
- A historical Medici Bank dataset for analysis exercises
- A dashboard and serving layer for KPIs, cash flow, and alerts
- Forensic scripts that look for vendor concentration, duplicate activity, Benford-style deviations, and round-number clustering

It is designed as a hands-on portfolio project for accounting, data engineering, and fraud-analysis practice.
```

## Slide-Ready Speaker Notes

- MediciMess is a Python project built around double-entry accounting and historical banking data.
- I started with the ledger itself, then added reports, import/export, and validation so the books can be checked end to end.
- I also built a historical transaction dataset and a pipeline that prepares analytics-ready outputs for dashboards.
- On the finance side, the project shows how debits and credits flow through a real accounting system.
- On the data side, it demonstrates cleaning, transformation, export, and API-style serving.
- On the forensic side, it highlights suspicious vendor concentration, duplicates, digit-pattern anomalies, and round-number behavior.
- The next steps would be a richer UI, role-based access control, and a more production-style storage layer.
