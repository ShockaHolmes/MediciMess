"""Duplicate transaction detection for the Medici Banking dataset.

Detects exact and near-duplicate ledger transactions by comparing:
- transaction date
- transaction description
- transaction amount
- debit account
- credit account

Outputs JSON alert records to data/serving/duplicate_transaction_analysis.json.

Usage:
    python duplicate_transaction_analysis.py [--input PATH] [--output PATH]
                                            [--date-window-days N]
                                            [--amount-tolerance DECIMAL]
                                            [--desc-similarity FLOAT]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "data" / "medici_transactions_cleaned.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "serving" / "duplicate_transaction_analysis.json"

DEFAULT_DATE_WINDOW_DAYS = 3
DEFAULT_AMOUNT_TOLERANCE = Decimal("1.00")
DEFAULT_DESC_SIMILARITY = 0.88


def parse_amount(value: str, field: str) -> Decimal:
    text = (value or "").strip()
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal for {field}: {value!r}") from exc


def parse_date(value: str) -> datetime.date:
    return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()


def normalize_description(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


def description_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_alert_record(
    alert_id: int,
    duplicate_type: str,
    severity: str,
    left: dict[str, Any],
    right: dict[str, Any],
    sim: float,
    amount_diff: Decimal,
    date_diff_days: int,
) -> dict[str, Any]:
    branch = left["branch"]
    period = left["date"][:7]
    threshold_desc = "exact-match" if duplicate_type == "EXACT" else f">={DEFAULT_DESC_SIMILARITY:.2f}"
    threshold_amount = "exact-match" if duplicate_type == "EXACT" else f"<={DEFAULT_AMOUNT_TOLERANCE:.2f}"

    return {
        "alert_id": alert_id,
        "rule": "C",
        "duplicate_type": duplicate_type,
        "severity": severity,
        "branch": branch,
        "period": period,
        "affected_transaction_ids": [left["id"], right["id"]],
        "counterparty": left.get("counterparty", ""),
        "date_left": left["date"],
        "date_right": right["date"],
        "date_diff_days": date_diff_days,
        "debit_account": left["debit_account"],
        "credit_account": left["credit_account"],
        "amount_left": f"{left['amount']:.2f}",
        "amount_right": f"{right['amount']:.2f}",
        "amount_diff": f"{amount_diff:.2f}",
        "description_left": left["description_raw"],
        "description_right": right["description_raw"],
        "description_similarity": round(sim, 4),
        "comparison": {
            "date_compared": True,
            "description_compared": True,
            "amount_compared": True,
            "debit_credit_compared": True,
            "description_threshold": threshold_desc,
            "amount_tolerance": threshold_amount,
        },
        "metric_value": round(sim, 4) if duplicate_type == "POSSIBLE" else 1.0,
        "threshold_value": DEFAULT_DESC_SIMILARITY if duplicate_type == "POSSIBLE" else 1.0,
        "description": (
            "Exact duplicate transaction pattern detected."
            if duplicate_type == "EXACT"
            else "Possible near-duplicate transaction pattern detected."
        ),
        "detected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "OPEN",
    }


def preprocess_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    for row in rows:
        try:
            tx_id = int((row.get("id") or "0").strip())
            tx_date = (row.get("date") or "").strip()
            debit_account = (row.get("debit_account") or "").strip()
            credit_account = (row.get("credit_account") or "").strip()
            amount = parse_amount(row.get("debit_amount", "0"), "debit_amount")
            description_raw = (row.get("description") or "").strip()
            description_norm = normalize_description(description_raw)
            parsed_date = parse_date(tx_date)
            branch = (row.get("branch") or "").strip() or "Unknown"
            counterparty = (row.get("counterparty") or "").strip()
        except (ValueError, InvalidOperation):
            continue

        if amount <= 0:
            continue
        if not debit_account or not credit_account:
            continue

        processed.append(
            {
                "id": tx_id,
                "branch": branch,
                "date": tx_date,
                "date_obj": parsed_date,
                "debit_account": debit_account,
                "credit_account": credit_account,
                "amount": amount,
                "description_raw": description_raw,
                "description_norm": description_norm,
                "counterparty": counterparty,
            }
        )
    return processed


def run_detection(
    rows: list[dict[str, str]],
    date_window_days: int,
    amount_tolerance: Decimal,
    desc_similarity_threshold: float,
) -> dict[str, Any]:
    processed = preprocess_rows(rows)

    # Block by branch + account pair to keep candidate set relevant and efficient.
    blocks: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in processed:
        key = (row["branch"], row["debit_account"], row["credit_account"])
        blocks[key].append(row)

    alerts: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, int]] = set()
    alert_id = 1
    exact_count = 0
    possible_count = 0

    for key, block_rows in sorted(blocks.items()):
        block_rows.sort(key=lambda row: (row["date_obj"], row["amount"], row["id"]))

        # 1) Exact duplicates: same date, same normalized description, same amount,
        # same debit and credit accounts (branch already in block key).
        exact_index: dict[tuple[str, str, Decimal], list[dict[str, Any]]] = defaultdict(list)
        for row in block_rows:
            ekey = (row["date"], row["description_norm"], row["amount"])
            exact_index[ekey].append(row)

        for group in exact_index.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda row: row["id"])
            for left_index in range(len(ordered) - 1):
                left = ordered[left_index]
                for right in ordered[left_index + 1 :]:
                    pair = tuple(sorted((left["id"], right["id"])))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    alerts.append(
                        build_alert_record(
                            alert_id=alert_id,
                            duplicate_type="EXACT",
                            severity="HIGH",
                            left=left,
                            right=right,
                            sim=1.0,
                            amount_diff=Decimal("0"),
                            date_diff_days=0,
                        )
                    )
                    exact_count += 1
                    alert_id += 1

        # 2) Possible duplicates: near date, near amount, similar description.
        for left_index in range(len(block_rows) - 1):
            left = block_rows[left_index]
            for right in block_rows[left_index + 1 :]:
                pair = tuple(sorted((left["id"], right["id"])))
                if pair in seen_pairs:
                    continue

                date_diff_days = abs((right["date_obj"] - left["date_obj"]).days)
                if date_diff_days > date_window_days:
                    # block_rows sorted by date; further rows only increase date diff.
                    break

                amount_diff = abs(right["amount"] - left["amount"])
                if amount_diff > amount_tolerance:
                    continue

                sim = description_similarity(left["description_norm"], right["description_norm"])
                if sim < desc_similarity_threshold:
                    continue

                seen_pairs.add(pair)
                severity = "HIGH" if sim >= 0.95 and amount_diff <= Decimal("0.10") else "MEDIUM"
                alerts.append(
                    build_alert_record(
                        alert_id=alert_id,
                        duplicate_type="POSSIBLE",
                        severity=severity,
                        left=left,
                        right=right,
                        sim=sim,
                        amount_diff=amount_diff,
                        date_diff_days=date_diff_days,
                    )
                )
                possible_count += 1
                alert_id += 1

    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    type_rank = {"EXACT": 0, "POSSIBLE": 1}
    alerts.sort(
        key=lambda rec: (
            type_rank.get(rec["duplicate_type"], 2),
            severity_rank.get(rec["severity"], 3),
            rec["date_left"],
            rec["affected_transaction_ids"][0],
        )
    )

    return {
        "meta": {
            "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "total_transactions": len(rows),
            "transactions_compared": len(processed),
            "block_count": len(blocks),
            "date_window_days": date_window_days,
            "amount_tolerance": f"{amount_tolerance:.2f}",
            "description_similarity_threshold": desc_similarity_threshold,
            "exact_duplicate_count": exact_count,
            "possible_duplicate_count": possible_count,
            "flagged_count": len(alerts),
        },
        "alerts": alerts,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def print_summary(report: dict[str, Any]) -> None:
    meta = report["meta"]
    alerts = report["alerts"]

    print()
    print("=" * 74)
    print("  Medici Bank — Duplicate Transaction Detection")
    print("=" * 74)
    print(f"  Run at                    : {meta['run_at']}")
    print(f"  Input transactions        : {meta['total_transactions']:,}")
    print(f"  Transactions compared     : {meta['transactions_compared']:,}")
    print(f"  Candidate blocks          : {meta['block_count']:,}")
    print(f"  Exact duplicates flagged  : {meta['exact_duplicate_count']:,}")
    print(f"  Possible duplicates flagged: {meta['possible_duplicate_count']:,}")
    print(f"  Total alerts              : {meta['flagged_count']:,}")
    print()

    if not alerts:
        print("  No duplicate patterns detected.")
        print()
        return

    print("  Sample alerts:")
    for alert in alerts[:20]:
        left_id, right_id = alert["affected_transaction_ids"]
        print(
            f"    [{alert['duplicate_type']}/{alert['severity']}] "
            f"{alert['branch']} {alert['date_left']} ids({left_id},{right_id}) "
            f"amtΔ={alert['amount_diff']} desc_sim={alert['description_similarity']:.3f}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect duplicate and near-duplicate transactions in the Medici ledger."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input cleaned CSV path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument(
        "--date-window-days",
        type=int,
        default=DEFAULT_DATE_WINDOW_DAYS,
        help="Maximum day difference for possible duplicates",
    )
    parser.add_argument(
        "--amount-tolerance",
        type=Decimal,
        default=DEFAULT_AMOUNT_TOLERANCE,
        help="Maximum amount difference for possible duplicates",
    )
    parser.add_argument(
        "--desc-similarity",
        type=float,
        default=DEFAULT_DESC_SIMILARITY,
        help="Minimum normalized description similarity for possible duplicates",
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

    print("Running duplicate transaction detection...")
    report = run_detection(
        rows=rows,
        date_window_days=args.date_window_days,
        amount_tolerance=args.amount_tolerance,
        desc_similarity_threshold=args.desc_similarity,
    )

    write_json(output_path, report)
    print(f"Report written to: {output_path}")
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
