"""Vendor concentration anomaly detection for the Medici Banking dataset.

Detects suspicious counterparties receiving unusually large shares of payments
within branch/account/period groupings.

Approach:
1. Filter expense-like payment transactions.
2. Group by (branch, period, debit_account).
3. For each vendor/counterparty, compute:
   - total amount
   - transaction count
   - share of group amount
4. Flag anomalies where vendor share exceeds threshold.
5. Store anomaly records and full group breakdown as JSON.

Usage:
    python vendor_concentration_analysis.py [--input PATH] [--output PATH]
                                           [--threshold FLOAT]
                                           [--high-threshold FLOAT]
                                           [--min-group-total FLOAT]
                                           [--min-group-transactions INT]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "data" / "medici_transactions_cleaned.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "serving" / "vendor_concentration_analysis.json"

# Rule-B aligned defaults from spec/serving layer.
DEFAULT_THRESHOLD = Decimal("0.05")      # Medium flag at >5%
DEFAULT_HIGH_THRESHOLD = Decimal("0.20") # High flag at >=20%
DEFAULT_MIN_GROUP_TOTAL = Decimal("1.00")
DEFAULT_MIN_GROUP_TRANSACTIONS = 5

EXPENSE_TYPES = {
    "operating_expense",
    "recurring_operating_expense",
    "vendor_payment",
}


def parse_amount(value: str, field: str) -> Decimal:
    text = (value or "").strip()
    if not text:
        return Decimal("0")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal for {field}: {value!r}") from exc
    return amount


def infer_account_type(account_name: str) -> str:
    """Infer account type using same naming conventions as serving layer."""
    text = (account_name or "").strip().casefold()
    if text.startswith("due from") or text in {"cash", "loans receivable", "political receivable"}:
        return "ASSET"
    if text in {"deposits payable", "accounts payable"}:
        return "LIABILITY"
    if text in {
        "wages",
        "rent",
        "maintenance",
        "courier services",
        "supplies",
        "security",
        "travel",
        "entertainment",
        "marketing",
        "depreciation",
        "miscellaneous expense",
    }:
        return "EXPENSE"
    if text in {"trading revenue", "exchange fee revenue", "interest income", "service revenue"}:
        return "REVENUE"
    return "UNKNOWN"


def is_vendor_payment_row(row: dict[str, str]) -> bool:
    tx_type = (row.get("type") or "").strip()
    debit_account = (row.get("debit_account") or "").strip()
    return tx_type in EXPENSE_TYPES and infer_account_type(debit_account) == "EXPENSE"


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def severity_for_share(share: Decimal, threshold: Decimal, high_threshold: Decimal) -> str | None:
    if share >= high_threshold:
        return "HIGH"
    if share > threshold:
        return "MEDIUM"
    return None


def run_detection(
    rows: list[dict[str, str]],
    threshold: Decimal,
    high_threshold: Decimal,
    min_group_total: Decimal,
    min_group_transactions: int,
) -> dict[str, Any]:
    """Run vendor concentration analysis and return JSON-serialisable report."""
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        if not is_vendor_payment_row(row):
            continue
        branch = (row.get("branch") or "").strip() or "Unknown"
        period = (row.get("date") or "")[:7] or "Unknown"
        debit_account = (row.get("debit_account") or "").strip() or "Unknown"
        grouped[(branch, period, debit_account)].append(row)

    anomaly_records: list[dict[str, Any]] = []
    all_groups: list[dict[str, Any]] = []
    alert_id = 1

    for (branch, period, debit_account), group_rows in sorted(grouped.items()):
        group_total = Decimal("0")
        by_vendor_amount: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_vendor_count: dict[str, int] = defaultdict(int)
        by_vendor_ids: dict[str, list[int]] = defaultdict(list)

        for row in group_rows:
            amount = parse_amount(row.get("debit_amount", "0"), "debit_amount")
            if amount <= 0:
                continue
            vendor = (row.get("counterparty") or "").strip() or "(blank counterparty)"
            group_total += amount
            by_vendor_amount[vendor] += amount
            by_vendor_count[vendor] += 1
            try:
                by_vendor_ids[vendor].append(int(row.get("id", "0")))
            except ValueError:
                pass

        total_transactions = sum(by_vendor_count.values())
        if group_total < min_group_total or total_transactions < min_group_transactions:
            continue

        vendors = []
        for vendor, amount in sorted(by_vendor_amount.items(), key=lambda item: item[1], reverse=True):
            share = (amount / group_total) if group_total > 0 else Decimal("0")
            vendors.append(
                {
                    "vendor": vendor,
                    "amount": f"{amount:.2f}",
                    "transaction_count": by_vendor_count[vendor],
                    "share": round(float(share), 6),
                    "share_pct": round(float(share * 100), 3),
                }
            )

            severity = severity_for_share(share, threshold, high_threshold)
            if severity is None:
                continue

            anomaly_records.append(
                {
                    "alert_id": alert_id,
                    "rule": "B",
                    "severity": severity,
                    "branch": branch,
                    "period": period,
                    "debit_account": debit_account,
                    "counterparty": vendor,
                    "metric_value": round(float(share), 6),
                    "threshold_value": float(threshold),
                    "group_total_amount": f"{group_total:.2f}",
                    "vendor_amount": f"{amount:.2f}",
                    "vendor_transaction_count": by_vendor_count[vendor],
                    "group_transaction_count": total_transactions,
                    "affected_transaction_ids": by_vendor_ids[vendor],
                    "description": (
                        f"Vendor concentration above {float(threshold) * 100:.1f}% "
                        f"for {debit_account} in {branch} ({period})."
                    ),
                    "detected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "status": "OPEN",
                }
            )
            alert_id += 1

        all_groups.append(
            {
                "branch": branch,
                "period": period,
                "debit_account": debit_account,
                "group_total_amount": f"{group_total:.2f}",
                "group_transaction_count": total_transactions,
                "top_vendor_share": vendors[0]["share"] if vendors else 0.0,
                "vendor_breakdown": vendors,
            }
        )

    # Keep highest risk records first.
    severity_rank = {"HIGH": 0, "MEDIUM": 1}
    anomaly_records.sort(
        key=lambda rec: (
            severity_rank.get(rec["severity"], 2),
            -rec["metric_value"],
            rec["branch"],
            rec["debit_account"],
        )
    )

    return {
        "meta": {
            "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "total_transactions": len(rows),
            "group_count": len(all_groups),
            "flagged_count": len(anomaly_records),
            "threshold": float(threshold),
            "high_threshold": float(high_threshold),
            "min_group_total": f"{min_group_total:.2f}",
            "min_group_transactions": min_group_transactions,
        },
        "anomalies": anomaly_records,
        "groups": all_groups,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def print_summary(report: dict[str, Any]) -> None:
    meta = report["meta"]
    anomalies = report["anomalies"]

    print()
    print("=" * 70)
    print("  Medici Bank — Vendor Concentration Detection")
    print("=" * 70)
    print(f"  Run at              : {meta['run_at']}")
    print(f"  Input transactions  : {meta['total_transactions']:,}")
    print(f"  Groups analysed     : {meta['group_count']:,}")
    print(f"  Groups flagged      : {meta['flagged_count']:,}")
    print(f"  Thresholds          : MEDIUM>{meta['threshold']:.2%}, HIGH>={meta['high_threshold']:.2%}")
    print()

    if not anomalies:
        print("  No suspicious vendor concentration patterns detected.")
        print()
        return

    print("  Top suspicious vendors:")
    for rec in anomalies[:15]:
        print(
            f"    [{rec['severity']}] {rec['branch']} {rec['period']} | "
            f"{rec['debit_account']} -> {rec['counterparty']} | "
            f"share={rec['metric_value']:.2%}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect suspicious vendor concentration in Medici transaction data."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input cleaned CSV path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument(
        "--threshold",
        type=Decimal,
        default=DEFAULT_THRESHOLD,
        help="MEDIUM severity share threshold (default: 0.05)",
    )
    parser.add_argument(
        "--high-threshold",
        type=Decimal,
        default=DEFAULT_HIGH_THRESHOLD,
        help="HIGH severity share threshold (default: 0.20)",
    )
    parser.add_argument(
        "--min-group-total",
        type=Decimal,
        default=DEFAULT_MIN_GROUP_TOTAL,
        help="Skip groups with total spend below this amount",
    )
    parser.add_argument(
        "--min-group-transactions",
        type=int,
        default=DEFAULT_MIN_GROUP_TRANSACTIONS,
        help="Skip groups with fewer transactions than this value",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    print(f"Loading transactions from: {input_path}")
    rows = load_rows(input_path)
    print(f"Loaded {len(rows):,} rows.")

    print("Running vendor concentration detection...")
    report = run_detection(
        rows=rows,
        threshold=args.threshold,
        high_threshold=args.high_threshold,
        min_group_total=args.min_group_total,
        min_group_transactions=args.min_group_transactions,
    )

    write_json(output_path, report)
    print(f"Report written to: {output_path}")
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
