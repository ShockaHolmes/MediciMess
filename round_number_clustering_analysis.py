"""Round-number clustering anomaly detection for the Medici Banking dataset.

Detects suspicious clustering of large round-number transactions by:
1. Identifying large round-valued amounts.
2. Grouping transactions by (branch, debit_account, counterparty).
3. Comparing each group's round-number frequency to global normal behavior.
4. Generating anomaly alerts for statistically elevated clustering.

Usage:
    python round_number_clustering_analysis.py [--input PATH] [--output PATH]
                                               [--min-large-amount DECIMAL]
                                               [--round-increment DECIMAL]
                                               [--min-group-size INT]
                                               [--min-round-count INT]
                                               [--min-uplift FLOAT]
                                               [--z-threshold FLOAT]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import sqrt
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "data" / "medici_transactions_cleaned.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "serving" / "round_number_clustering_analysis.json"

DEFAULT_MIN_LARGE_AMOUNT = Decimal("1000")
DEFAULT_ROUND_INCREMENT = Decimal("500")
DEFAULT_MIN_GROUP_SIZE = 8
DEFAULT_MIN_ROUND_COUNT = 4
DEFAULT_MIN_UPLIFT = 0.15
DEFAULT_Z_THRESHOLD = 2.0


def parse_amount(value: str, field: str) -> Decimal:
    text = (value or "").strip()
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal for {field}: {value!r}") from exc


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def is_large_round_value(amount: Decimal, min_large_amount: Decimal, round_increment: Decimal) -> bool:
    if amount < min_large_amount:
        return False
    cents = (amount * 100).quantize(Decimal("1"))
    step_cents = (round_increment * 100).quantize(Decimal("1"))
    if step_cents <= 0:
        return False
    return cents % step_cents == 0


def normal_approx_z_score(k: int, n: int, p: float) -> float:
    """Binomial normal approximation z-score for observed round count."""
    if n <= 0 or p <= 0 or p >= 1:
        return 0.0
    mean = n * p
    variance = n * p * (1 - p)
    if variance <= 0:
        return 0.0
    return (k - mean) / sqrt(variance)


def build_alert(
    alert_id: int,
    key: tuple[str, str, str],
    group_rows: list[dict[str, str]],
    round_ids: list[int],
    round_count: int,
    group_total: int,
    round_share: float,
    global_round_share: float,
    z_score: float,
    min_uplift: float,
    z_threshold: float,
) -> dict[str, Any]:
    branch, debit_account, counterparty = key
    uplift = round_share - global_round_share

    severity = "MEDIUM"
    if round_share >= 0.60 or z_score >= 3.0:
        severity = "HIGH"

    return {
        "alert_id": alert_id,
        "rule": "D",
        "severity": severity,
        "branch": branch,
        "debit_account": debit_account,
        "counterparty": counterparty,
        "period": "ALL",
        "affected_transaction_ids": round_ids,
        "round_count": round_count,
        "group_transaction_count": group_total,
        "round_share": round(round_share, 6),
        "round_share_pct": round(round_share * 100, 3),
        "baseline_round_share": round(global_round_share, 6),
        "baseline_round_share_pct": round(global_round_share * 100, 3),
        "uplift": round(uplift, 6),
        "uplift_pct_points": round(uplift * 100, 3),
        "z_score": round(z_score, 4),
        "thresholds": {
            "min_uplift": min_uplift,
            "z_threshold": z_threshold,
        },
        "description": (
            f"Round-number clustering detected for {debit_account} / {counterparty} "
            f"in {branch}: {round_share * 100:.1f}% round-valued large transactions "
            f"vs {global_round_share * 100:.1f}% baseline."
        ),
        "detected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "OPEN",
    }


def run_detection(
    rows: list[dict[str, str]],
    min_large_amount: Decimal,
    round_increment: Decimal,
    min_group_size: int,
    min_round_count: int,
    min_uplift: float,
    z_threshold: float,
) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    candidate_rows: list[dict[str, str]] = []

    for row in rows:
        try:
            amount = parse_amount(row.get("debit_amount", "0"), "debit_amount")
        except ValueError:
            continue
        if amount <= 0:
            continue
        if amount < min_large_amount:
            continue

        branch = (row.get("branch") or "").strip() or "Unknown"
        debit_account = (row.get("debit_account") or "").strip() or "Unknown"
        counterparty = (row.get("counterparty") or "").strip() or "(blank counterparty)"

        grouped_row = dict(row)
        grouped_row["_amount"] = str(amount)
        groups[(branch, debit_account, counterparty)].append(grouped_row)
        candidate_rows.append(grouped_row)

    # Baseline: fraction of large transactions that are round-valued globally.
    global_round_count = 0
    for row in candidate_rows:
        amount = Decimal(row["_amount"])
        if is_large_round_value(amount, min_large_amount, round_increment):
            global_round_count += 1

    global_total = len(candidate_rows)
    global_round_share = (global_round_count / global_total) if global_total > 0 else 0.0

    alerts: list[dict[str, Any]] = []
    all_groups: list[dict[str, Any]] = []
    alert_id = 1

    for key, group_rows in sorted(groups.items()):
        group_total = len(group_rows)
        if group_total < min_group_size:
            continue

        round_count = 0
        round_ids: list[int] = []
        sample_ids: list[int] = []

        for row in group_rows:
            try:
                tx_id = int(row.get("id", "0"))
            except ValueError:
                tx_id = 0
            if tx_id:
                sample_ids.append(tx_id)

            amount = Decimal(row["_amount"])
            if is_large_round_value(amount, min_large_amount, round_increment):
                round_count += 1
                if tx_id:
                    round_ids.append(tx_id)

        round_share = (round_count / group_total) if group_total > 0 else 0.0
        uplift = round_share - global_round_share
        z_score = normal_approx_z_score(round_count, group_total, global_round_share)

        all_groups.append(
            {
                "branch": key[0],
                "debit_account": key[1],
                "counterparty": key[2],
                "group_transaction_count": group_total,
                "round_count": round_count,
                "round_share": round(round_share, 6),
                "round_share_pct": round(round_share * 100, 3),
                "baseline_round_share": round(global_round_share, 6),
                "baseline_round_share_pct": round(global_round_share * 100, 3),
                "uplift": round(uplift, 6),
                "uplift_pct_points": round(uplift * 100, 3),
                "z_score": round(z_score, 4),
                "sample_transaction_ids": sample_ids[:20],
            }
        )

        if round_count < min_round_count:
            continue
        if uplift < min_uplift:
            continue
        if z_score < z_threshold and round_share < 0.45:
            continue

        alerts.append(
            build_alert(
                alert_id=alert_id,
                key=key,
                group_rows=group_rows,
                round_ids=round_ids,
                round_count=round_count,
                group_total=group_total,
                round_share=round_share,
                global_round_share=global_round_share,
                z_score=z_score,
                min_uplift=min_uplift,
                z_threshold=z_threshold,
            )
        )
        alert_id += 1

    severity_rank = {"HIGH": 0, "MEDIUM": 1}
    alerts.sort(
        key=lambda rec: (
            severity_rank.get(rec["severity"], 2),
            -rec["round_share"],
            -rec["z_score"],
            rec["branch"],
        )
    )

    all_groups.sort(key=lambda g: (-g["round_share"], -g["z_score"], g["branch"]))

    return {
        "meta": {
            "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "total_transactions": len(rows),
            "candidate_large_transactions": global_total,
            "global_round_count": global_round_count,
            "global_round_share": round(global_round_share, 6),
            "global_round_share_pct": round(global_round_share * 100, 3),
            "group_count": len(all_groups),
            "flagged_count": len(alerts),
            "min_large_amount": f"{min_large_amount:.2f}",
            "round_increment": f"{round_increment:.2f}",
            "min_group_size": min_group_size,
            "min_round_count": min_round_count,
            "min_uplift": min_uplift,
            "z_threshold": z_threshold,
        },
        "alerts": alerts,
        "groups": all_groups,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def print_summary(report: dict[str, Any]) -> None:
    meta = report["meta"]
    alerts = report["alerts"]

    print()
    print("=" * 78)
    print("  Medici Bank — Round-Number Clustering Detection")
    print("=" * 78)
    print(f"  Run at                     : {meta['run_at']}")
    print(f"  Input transactions         : {meta['total_transactions']:,}")
    print(f"  Candidate large tx         : {meta['candidate_large_transactions']:,}")
    print(f"  Global round baseline      : {meta['global_round_share_pct']:.2f}%")
    print(f"  Groups analysed            : {meta['group_count']:,}")
    print(f"  Alerts generated           : {meta['flagged_count']:,}")
    print()

    if not alerts:
        print("  No suspicious round-number clustering detected.")
        print()
        return

    print("  Top alerts:")
    for rec in alerts[:15]:
        print(
            f"    [{rec['severity']}] {rec['branch']} | {rec['debit_account']} | {rec['counterparty']} "
            f"-> round_share={rec['round_share_pct']:.2f}% baseline={rec['baseline_round_share_pct']:.2f}% "
            f"z={rec['z_score']:.2f}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect suspicious clustering of large round-number transactions."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input cleaned CSV path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument(
        "--min-large-amount",
        type=Decimal,
        default=DEFAULT_MIN_LARGE_AMOUNT,
        help="Minimum transaction amount considered 'large'",
    )
    parser.add_argument(
        "--round-increment",
        type=Decimal,
        default=DEFAULT_ROUND_INCREMENT,
        help="Round-value increment (e.g., 500 means multiples of 500)",
    )
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=DEFAULT_MIN_GROUP_SIZE,
        help="Minimum transactions in a (branch, account, vendor) group",
    )
    parser.add_argument(
        "--min-round-count",
        type=int,
        default=DEFAULT_MIN_ROUND_COUNT,
        help="Minimum round-number transactions required in a group",
    )
    parser.add_argument(
        "--min-uplift",
        type=float,
        default=DEFAULT_MIN_UPLIFT,
        help="Minimum absolute increase above baseline round share",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=DEFAULT_Z_THRESHOLD,
        help="Minimum z-score for statistical elevation",
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

    print("Running round-number clustering detection...")
    report = run_detection(
        rows=rows,
        min_large_amount=args.min_large_amount,
        round_increment=args.round_increment,
        min_group_size=args.min_group_size,
        min_round_count=args.min_round_count,
        min_uplift=args.min_uplift,
        z_threshold=args.z_threshold,
    )

    write_json(output_path, report)
    print(f"Report written to: {output_path}")
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
