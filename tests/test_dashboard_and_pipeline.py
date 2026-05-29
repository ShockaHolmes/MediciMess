"""Tests for the dashboard data layer and pipeline ingestion."""

import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from medici_banking import Ledger, AccountType, TransactionEntry


def _seed():
    led = Ledger("Test Bank")
    led._silent_mode = True
    cash  = led.create_account("Cash", AccountType.ASSET)
    ar    = led.create_account("Accounts Receivable", AccountType.ASSET)
    cap   = led.create_account("Capital", AccountType.EQUITY)
    rev   = led.create_account("Interest Income", AccountType.REVENUE)
    wages = led.create_account("Wages", AccountType.EXPENSE)

    led.record_transaction(date(1397, 1, 15), "Investment",
        TransactionEntry.debit(cash, Decimal("10000")),
        TransactionEntry.credit(cap, Decimal("10000")),
        branch="Florence")
    led.record_transaction(date(1397, 2, 10), "Loan out",
        TransactionEntry.debit(ar, Decimal("2000")),
        TransactionEntry.credit(cash, Decimal("2000")),
        branch="Florence")
    led.record_transaction(date(1397, 3, 5), "Interest received",
        TransactionEntry.debit(cash, Decimal("300")),
        TransactionEntry.credit(rev, Decimal("300")),
        branch="Rome")
    led.record_transaction(date(1397, 3, 20), "Wages",
        TransactionEntry.debit(wages, Decimal("400")),
        TransactionEntry.credit(cash, Decimal("400")),
        branch="Florence")
    return led


# KPI metrics ---------------------------------------------------------------

def test_kpi_metrics_reflect_processed_data():
    led = _seed()
    k = led.get_kpi_metrics()
    assert k["total_assets"] == Decimal("9900.00")          # cash 7900 + AR 2000
    assert k["cash_on_hand"] == Decimal("7900.00")          # 10000 - 2000 + 300 - 400
    assert k["loans_outstanding"] == Decimal("2000.00")
    assert k["net_income"] == Decimal("-100.00")            # 300 rev - 400 exp
    assert k["transaction_count"] == 4
    assert k["account_count"] == 5


# Cash flow series ----------------------------------------------------------

def test_cash_flow_series_monthly_buckets():
    led = _seed()
    rows = led.get_cash_flow_series()
    by_period = {r["period"]: r for r in rows}
    # Jan: +10000 in
    assert by_period["1397-01"]["inflow"]  == Decimal("10000.00")
    assert by_period["1397-01"]["outflow"] == Decimal("0.00")
    # Feb: -2000 out (loan out)
    assert by_period["1397-02"]["outflow"] == Decimal("2000.00")
    # Mar: +300 in, -400 out, net -100
    assert by_period["1397-03"]["inflow"]  == Decimal("300.00")
    assert by_period["1397-03"]["outflow"] == Decimal("400.00")
    assert by_period["1397-03"]["net"]     == Decimal("-100.00")


def test_cash_flow_series_filters_by_branch():
    led = _seed()
    florence = led.get_cash_flow_series(branch="Florence")
    rome     = led.get_cash_flow_series(branch="Rome")
    flo_periods = {r["period"] for r in florence}
    rome_periods = {r["period"] for r in rome}
    assert "1397-01" in flo_periods   # Florence investment
    assert "1397-01" not in rome_periods
    assert rome_periods == {"1397-03"} # Rome only saw the interest deposit


# Transactions table --------------------------------------------------------

def test_transactions_table_newest_first_with_limit():
    led = _seed()
    rows = led.get_transactions_table(limit=2)
    assert len(rows) == 2
    assert rows[0]["description"] == "Wages"               # most recent
    assert rows[1]["description"] == "Interest received"


def test_transactions_table_search_is_case_insensitive():
    led = _seed()
    rows = led.get_transactions_table(search="LOAN")
    assert len(rows) == 1
    assert rows[0]["description"] == "Loan out"


# Alerts --------------------------------------------------------------------

def test_alerts_flag_negative_income():
    led = _seed()
    alerts = led.get_alerts(low_cash_threshold=Decimal("0"))  # disable cash alert
    levels = {a["source"]: a["level"] for a in alerts}
    assert levels.get("income") == "warning"
    assert "integrity" not in levels                        # books still balance


def test_alerts_flag_low_cash():
    led = _seed()
    alerts = led.get_alerts(low_cash_threshold=Decimal("100000"))
    sources = {a["source"] for a in alerts}
    assert "liquidity" in sources


# Dashboard bundle ----------------------------------------------------------

def test_dashboard_data_returns_all_sections():
    led = _seed()
    d = led.get_dashboard_data()
    assert set(d.keys()) == {
        "kpis", "cash_flow", "recent_transactions", "alerts", "balance_sheet"
    }


# Pipeline ingestion --------------------------------------------------------

def test_ingest_file_dispatches_by_extension_and_logs(tmp_path, caplog):
    src = _seed()
    f = tmp_path / "data" / "raw" / "txns.json"
    src.export_transactions_to_json(str(f))

    dst = Ledger("Pipeline target")
    dst._silent_mode = True
    with caplog.at_level(logging.INFO, logger="medici_banking"):
        count = dst.ingest_file(str(f))
    assert count == 4
    # Logger emitted a success entry referencing the file.
    assert any("Ingested 4" in r.message for r in caplog.records)
    # Raw file is preserved (ingestion doesn't modify or delete).
    assert f.exists()


def test_ingest_file_rejects_unsupported_extension(tmp_path):
    led = Ledger("X")
    led._silent_mode = True
    f = tmp_path / "data.txt"
    f.write_text("not a supported format")
    with pytest.raises(ValueError, match="Unsupported file type"):
        led.ingest_file(str(f))


def test_ingest_file_missing_path_raises_and_logs(tmp_path, caplog):
    led = Ledger("X")
    led._silent_mode = True
    with caplog.at_level(logging.ERROR, logger="medici_banking"):
        with pytest.raises(FileNotFoundError):
            led.ingest_file(str(tmp_path / "nope.json"))
    assert any("file not found" in r.message for r in caplog.records)


# Branch round-trip through JSON --------------------------------------------

def test_branch_survives_json_roundtrip(tmp_path):
    src = _seed()
    f = tmp_path / "out.json"
    src.export_transactions_to_json(str(f))
    dst = Ledger("Restored"); dst._silent_mode = True
    dst.import_transactions_from_json(str(f))
    branches = {t.branch for t in dst.transactions}
    assert branches == {"Florence", "Rome"}
