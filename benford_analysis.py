"""Benford's Law anomaly detection for the Medici Banking dataset.

Reads the cleaned transaction CSV, groups transactions by four dimensions
(debit account, credit account, counterparty/vendor, and branch), computes
the observed vs expected first-significant-digit distributions, and flags
groups whose distributions deviate from Benford's Law using two independent
statistics:

  MAD  — Mean Absolute Deviation (threshold: 0.015 MEDIUM, 0.030 HIGH)
  χ²   — Chi-squared statistic against 8 degrees of freedom
          (threshold: 15.507 at α=0.05, 20.090 at α=0.01)

Writes a structured anomaly report to data/serving/benford_analysis.json and
prints a human-readable summary to stdout.

Usage:
    python benford_analysis.py [--input PATH] [--output PATH] [--min-samples N]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "data" / "medici_transactions_cleaned.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "serving" / "benford_analysis.json"

# ---------------------------------------------------------------------------
# Benford's Law constants
# ---------------------------------------------------------------------------

# Theoretical probabilities P(d) = log10(1 + 1/d) for d in 1..9
BENFORD: dict[int, float] = {d: math.log10(1 + 1 / d) for d in range(1, 10)}

# Chi-squared critical values for 8 degrees of freedom (9 digit classes – 1 constraint)
CHI2_CRITICAL_005 = 15.507   # α = 0.05  (MEDIUM severity threshold)
CHI2_CRITICAL_001 = 20.090   # α = 0.01  (HIGH severity threshold)

MAD_THRESHOLD_MEDIUM = 0.015
MAD_THRESHOLD_HIGH   = 0.030

DEFAULT_MIN_SAMPLES = 30  # minimum transactions per group for a reliable result


# ---------------------------------------------------------------------------
# Core statistical functions — no external dependencies
# ---------------------------------------------------------------------------

def first_significant_digit(amount_str: str) -> int | None:
    """Return the first non-zero digit of a decimal amount string, or None."""
    for ch in amount_str:
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


def expected_distribution() -> dict[int, float]:
    """Return the theoretical Benford distribution {1: 0.301, …, 9: 0.046}."""
    return dict(BENFORD)


def observed_distribution(digits: list[int]) -> dict[int, int]:
    """Count occurrences of each leading digit (1-9) in *digits*."""
    counts: dict[int, int] = {d: 0 for d in range(1, 10)}
    for d in digits:
        if 1 <= d <= 9:
            counts[d] += 1
    return counts


def mean_absolute_deviation(obs: dict[int, int], total: int) -> float:
    """MAD = (1/9) * Σ |p_obs(d) – p_expected(d)| for d in 1..9."""
    if total == 0:
        return 0.0
    return sum(abs((obs.get(d, 0) / total) - BENFORD[d]) for d in range(1, 10)) / 9


def chi_squared_statistic(obs: dict[int, int], total: int) -> float:
    """χ² = Σ (O – E)² / E  where E = total × P_benford(d)."""
    if total == 0:
        return 0.0
    stat = 0.0
    for d in range(1, 10):
        expected_count = total * BENFORD[d]
        if expected_count == 0:
            continue
        observed_count = obs.get(d, 0)
        stat += (observed_count - expected_count) ** 2 / expected_count
    return stat


def severity_from_stats(mad: float, chi2: float) -> str | None:
    """Return 'HIGH', 'MEDIUM', or None (not suspicious)."""
    if mad >= MAD_THRESHOLD_HIGH or chi2 >= CHI2_CRITICAL_001:
        return "HIGH"
    if mad >= MAD_THRESHOLD_MEDIUM or chi2 >= CHI2_CRITICAL_005:
        return "MEDIUM"
    return None


# ---------------------------------------------------------------------------
# Per-group analysis
# ---------------------------------------------------------------------------

def analyze_group(
    dimension: str,
    group_key: str,
    rows: list[dict[str, str]],
    amount_field: str = "debit_amount",
) -> dict[str, Any] | None:
    """
    Analyse a single group of transactions for Benford compliance.

    Returns a result dict if the group is large enough, else None.
    The result is flagged only when severity is non-None (suspicious).
    """
    digits: list[int] = []
    transaction_ids: list[int] = []

    for row in rows:
        raw = (row.get(amount_field) or "").strip()
        if not raw or raw in {"0", "0.00", "0.0"}:
            continue
        d = first_significant_digit(raw)
        if d is not None:
            digits.append(d)
            try:
                transaction_ids.append(int(row["id"]))
            except (KeyError, ValueError):
                pass

    total = len(digits)
    if total < DEFAULT_MIN_SAMPLES:
        return None

    obs = observed_distribution(digits)
    mad = mean_absolute_deviation(obs, total)
    chi2 = chi_squared_statistic(obs, total)
    svr = severity_from_stats(mad, chi2)

    # Build per-digit table for reporting
    digit_table = [
        {
            "digit": d,
            "expected_pct": round(BENFORD[d] * 100, 3),
            "observed_count": obs[d],
            "observed_pct": round((obs[d] / total) * 100, 3) if total else 0.0,
            "deviation_pct": round(abs((obs[d] / total) - BENFORD[d]) * 100, 3) if total else 0.0,
        }
        for d in range(1, 10)
    ]

    return {
        "dimension": dimension,
        "group_key": group_key,
        "amount_field": amount_field,
        "sample_count": total,
        "mad": round(mad, 6),
        "chi_squared": round(chi2, 4),
        "chi_squared_critical_005": CHI2_CRITICAL_005,
        "chi_squared_critical_001": CHI2_CRITICAL_001,
        "suspicious": svr is not None,
        "severity": svr or "OK",
        "digit_distribution": digit_table,
        "sample_transaction_ids": transaction_ids[:50],
        "description": _build_description(dimension, group_key, mad, chi2, svr),
    }


def _build_description(
    dimension: str,
    group_key: str,
    mad: float,
    chi2: float,
    severity: str | None,
) -> str:
    if severity is None:
        return (
            f"{dimension} '{group_key}' conforms to Benford's Law "
            f"(MAD={mad:.4f}, χ²={chi2:.2f})."
        )
    level = "significantly" if severity == "HIGH" else "moderately"
    return (
        f"{dimension} '{group_key}' {level} deviates from Benford's Law — "
        f"MAD={mad:.4f} (threshold {MAD_THRESHOLD_MEDIUM}), "
        f"χ²={chi2:.2f} (critical {CHI2_CRITICAL_005} at α=0.05). "
        "Possible constructed or manipulated amounts."
    )


# ---------------------------------------------------------------------------
# Dataset grouping
# ---------------------------------------------------------------------------

def group_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], list[dict[str, str]]]:
    """
    Return a mapping of (dimension, group_key, amount_field) → row list.

    Dimensions analysed:
      - debit_account  (account receiving the debit — amounts from debit_amount)
      - credit_account (account receiving the credit — amounts from credit_amount)
      - counterparty   (vendor/payee — amounts from debit_amount)
      - branch         (branch office — amounts from debit_amount)
    """
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        branch = (row.get("branch") or "").strip()
        debit_acct = (row.get("debit_account") or "").strip()
        credit_acct = (row.get("credit_account") or "").strip()
        counterparty = (row.get("counterparty") or "").strip()

        if debit_acct:
            groups[("Debit Account", debit_acct, "debit_amount")].append(row)
        if credit_acct:
            groups[("Credit Account", credit_acct, "credit_amount")].append(row)
        if counterparty:
            groups[("Vendor/Counterparty", counterparty, "debit_amount")].append(row)
        if branch:
            groups[("Branch", branch, "debit_amount")].append(row)

    return groups


# ---------------------------------------------------------------------------
# Main analysis runner
# ---------------------------------------------------------------------------

def run_analysis(
    rows: list[dict[str, str]],
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> dict[str, Any]:
    """
    Run the full Benford's Law analysis across all grouping dimensions.

    Returns a report dict suitable for JSON serialisation.
    """
    global DEFAULT_MIN_SAMPLES
    DEFAULT_MIN_SAMPLES = min_samples  # propagate to analyze_group

    groups = group_rows(rows)

    all_results: list[dict[str, Any]] = []
    groups_analysed = 0
    flagged = 0

    for (dimension, group_key, amount_field), group_rows_list in sorted(groups.items()):
        result = analyze_group(dimension, group_key, group_rows_list, amount_field)
        if result is None:
            continue
        groups_analysed += 1
        all_results.append(result)
        if result["suspicious"]:
            flagged += 1

    # Sort: suspicious first, then by severity (HIGH before MEDIUM), then by MAD desc
    severity_order = {"HIGH": 0, "MEDIUM": 1, "OK": 2}
    all_results.sort(
        key=lambda r: (0 if r["suspicious"] else 1, severity_order.get(r["severity"], 2), -r["mad"])
    )

    flagged_records = [r for r in all_results if r["suspicious"]]

    return {
        "meta": {
            "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "total_transactions": len(rows),
            "min_samples_threshold": min_samples,
            "mad_threshold_medium": MAD_THRESHOLD_MEDIUM,
            "mad_threshold_high": MAD_THRESHOLD_HIGH,
            "chi2_critical_005": CHI2_CRITICAL_005,
            "chi2_critical_001": CHI2_CRITICAL_001,
            "chi2_degrees_of_freedom": 8,
            "groups_analysed": groups_analysed,
            "groups_flagged": flagged,
        },
        "flagged_groups": flagged_records,
        "all_groups": all_results,
    }


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_cleaned_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


def print_summary(report: dict[str, Any]) -> None:
    meta = report["meta"]
    flagged = report["flagged_groups"]

    print()
    print("=" * 65)
    print("  Medici Bank — Benford's Law Anomaly Detection Report")
    print("=" * 65)
    print(f"  Run at           : {meta['run_at']}")
    print(f"  Transactions     : {meta['total_transactions']:,}")
    print(f"  Min sample size  : {meta['min_samples_threshold']}")
    print(f"  Groups analysed  : {meta['groups_analysed']}")
    print(f"  Groups flagged   : {meta['groups_flagged']}")
    print()

    if not flagged:
        print("  No suspicious groups detected.")
        print()
        return

    # Group by dimension for readable output
    by_dim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in flagged:
        by_dim[rec["dimension"]].append(rec)

    for dim in sorted(by_dim):
        print(f"  [{dim}]")
        for rec in by_dim[dim]:
            sev_tag = f"[{rec['severity']}]"
            print(
                f"    {sev_tag:<8}  {rec['group_key']:<40}  "
                f"n={rec['sample_count']:>6,}  "
                f"MAD={rec['mad']:.4f}  χ²={rec['chi_squared']:.2f}"
            )
        print()

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benford's Law anomaly detection for the Medici Banking dataset."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        metavar="PATH",
        help=f"Path to cleaned transaction CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        metavar="PATH",
        help=f"Path for the JSON report (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=DEFAULT_MIN_SAMPLES,
        metavar="N",
        help=f"Minimum transactions per group (default: {DEFAULT_MIN_SAMPLES})",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    min_samples = args.min_samples

    print(f"Loading transactions from: {input_path}")
    rows = load_cleaned_csv(input_path)
    print(f"Loaded {len(rows):,} rows.")

    print("Running Benford's Law analysis …")
    report = run_analysis(rows, min_samples=min_samples)

    write_report(report, output_path)
    print(f"Report written to: {output_path}")

    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
