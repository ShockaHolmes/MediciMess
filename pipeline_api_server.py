"""Lightweight HTTP API for the Medici data serving layer.

This server reads precomputed serving-layer outputs from data/serving and exposes
REST endpoints for the dashboard and reports.

Endpoints:
- GET /health
- GET /api
- GET /api/transactions?branch=&start=&end=&type=&page=&per_page=
- GET /api/kpis?branch=&start=&end=
- GET /api/accounts?account_type=&name=
- GET /api/cashflow?branch=&start=&end=&granularity=
- GET /api/alerts?branch=&start=&end=&severity=
- GET /api/duplicates?branch=&start=&end=&severity=&duplicate_type=&page=&per_page=
- GET /api/vendor-concentration?branch=&start=&end=&severity=&counterparty=&debit_account=&page=&per_page=
- GET /api/benford?severity=&dimension=&group_key=&flagged_only=&page=&per_page=
- GET /api/round-clustering?branch=&severity=&counterparty=&debit_account=&flagged_only=&page=&per_page=
- POST /api/alerts/{id}/acknowledge
- GET /api/loans?branch=&status=
- GET /api/expenses?branch=&start=&end=
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
SERVING_DIR = BASE_DIR / "data" / "serving"
API_DIR = SERVING_DIR / "api"


class ServingStore:
    def __init__(self, serving_dir: Path, api_dir: Path):
        self.serving_dir = serving_dir
        self.api_dir = api_dir
        self.transactions = self._load_json(serving_dir / "analytics_ready_transactions.json")
        self.branch_summary = self._load_json(serving_dir / "branch_summary.json")
        self.account_summary = self._load_json(serving_dir / "account_summary.json")
        self.monthly_kpis = self._load_json(serving_dir / "monthly_kpi_summary.json")
        self.expenses = self._load_json(serving_dir / "expense_breakdown.json")
        self.loans = self._load_json(serving_dir / "loan_portfolio.json")
        self.alerts = self._load_json(api_dir / "api_alerts.json").get("data", [])
        self.duplicate_alerts = self._load_json(serving_dir / "duplicate_transaction_analysis.json").get("alerts", [])
        self.vendor_concentration = self._load_json(serving_dir / "vendor_concentration_analysis.json")
        self.benford_analysis = self._load_json(serving_dir / "benford_analysis.json")
        self.round_clustering = self._load_json(serving_dir / "round_number_clustering_analysis.json")
        self.alert_status_overrides: dict[int, dict[str, Any]] = {}

    @staticmethod
    def _load_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _parse_int(value: str | None, default: int) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except ValueError:
            return default

    @staticmethod
    def _parse_bool(value: str | None, default: bool) -> bool:
        if value is None or value == "":
            return default
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _parse_period(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value + "-01", "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _money_sum(rows: list[dict[str, Any]], field: str) -> Decimal:
        total = Decimal("0")
        for row in rows:
            try:
                total += Decimal(str(row.get(field, "0")))
            except Exception:
                continue
        return total.quantize(Decimal("0.01"))

    def _branch_filter(self, rows: list[dict[str, Any]], branch: str | None) -> list[dict[str, Any]]:
        if not branch:
            return list(rows)
        return [row for row in rows if row.get("branch") == branch]

    def _date_filter(self, rows: list[dict[str, Any]], start: str | None, end: str | None) -> list[dict[str, Any]]:
        start_dt = self._parse_date(start)
        end_dt = self._parse_date(end)
        if not start_dt and not end_dt:
            return list(rows)

        filtered = []
        for row in rows:
            row_dt = self._parse_date(row.get("date") or row.get("first_date") or row.get("period") or "")
            if row_dt is None:
                if row.get("period"):
                    try:
                        row_dt = datetime.strptime(row["period"] + "-01", "%Y-%m-%d")
                    except ValueError:
                        continue
                else:
                    continue
            if start_dt and row_dt < start_dt:
                continue
            if end_dt and row_dt > end_dt:
                continue
            filtered.append(row)
        return filtered

    def get_transactions(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None
        tx_type = (params.get("type") or [""])[0] or None
        page = self._parse_int((params.get("page") or [None])[0], 1)
        per_page = self._parse_int((params.get("per_page") or [None])[0], 100)
        per_page = max(1, min(per_page, 1000))
        page = max(1, page)

        rows = self._branch_filter(self.transactions, branch)
        rows = self._date_filter(rows, start, end)
        if tx_type:
            rows = [row for row in rows if row.get("type") == tx_type]

        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        page_rows = rows[start_index : start_index + per_page]
        return {
            "branch": branch,
            "start": start,
            "end": end,
            "type": tx_type,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "data": page_rows,
        }

    def get_kpis(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None

        rows = self._branch_filter(self.monthly_kpis, branch)
        rows = self._date_filter(rows, start, end)

        if not rows:
            return {
                "branch": branch,
                "start": start,
                "end": end,
                "data": {},
            }

        summary = {
            "branch": branch,
            "start": start,
            "end": end,
            "period_count": len(rows),
            "transaction_count": sum(int(row.get("transaction_count", 0)) for row in rows),
            "cash_inflows": f"{self._money_sum(rows, 'cash_inflows'):.2f}",
            "cash_outflows": f"{self._money_sum(rows, 'cash_outflows'):.2f}",
            "net_cash_movement": f"{self._money_sum(rows, 'net_cash_movement'):.2f}",
            "closing_cash_balance": f"{self._money_sum(rows, 'closing_cash_balance'):.2f}",
            "deposits": f"{self._money_sum(rows, 'deposits'):.2f}",
            "withdrawals": f"{self._money_sum(rows, 'withdrawals'):.2f}",
            "loans_issued": f"{self._money_sum(rows, 'loans_issued'):.2f}",
            "loans_repaid": f"{self._money_sum(rows, 'loans_repaid'):.2f}",
            "loan_portfolio_balance": f"{self._money_sum(rows, 'loan_portfolio_balance'):.2f}",
            "interest_earned": f"{self._money_sum(rows, 'interest_earned'):.2f}",
            "operating_expenses": f"{self._money_sum(rows, 'operating_expenses'):.2f}",
            "trading_revenue": f"{self._money_sum(rows, 'trading_revenue'):.2f}",
            "exchange_fee_revenue": f"{self._money_sum(rows, 'exchange_fee_revenue'):.2f}",
            "interest_income": f"{self._money_sum(rows, 'interest_income'):.2f}",
            "total_revenue": f"{self._money_sum(rows, 'total_revenue'):.2f}",
            "net_income": f"{self._money_sum(rows, 'net_income'):.2f}",
        }
        return summary

    def get_cashflow(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None
        granularity = (params.get("granularity") or ["month"])[0] or "month"

        rows = self._branch_filter(self.monthly_kpis, branch)
        rows = self._date_filter(rows, start, end)
        data = [
            {
                "branch": row.get("branch"),
                "period": row.get("period"),
                "granularity": granularity,
                "cash_inflows": row.get("cash_inflows"),
                "cash_outflows": row.get("cash_outflows"),
                "net_cash_movement": row.get("net_cash_movement"),
                "closing_cash_balance": row.get("closing_cash_balance"),
            }
            for row in rows
        ]
        return {
            "branch": branch,
            "start": start,
            "end": end,
            "granularity": granularity,
            "data": data,
        }

    def get_loans(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        status = (params.get("status") or [""])[0] or None
        rows = self._branch_filter(self.loans, branch)
        if status:
            rows = [row for row in rows if row.get("status") == status.upper()]
        return {
            "branch": branch,
            "status": status,
            "total": len(rows),
            "data": rows,
        }

    def get_expenses(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None
        rows = self._branch_filter(self.expenses, branch)
        rows = self._date_filter(rows, start, end)
        return {
            "branch": branch,
            "start": start,
            "end": end,
            "total": len(rows),
            "data": rows,
        }

    def get_alerts(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None
        severity = (params.get("severity") or [""])[0] or None

        rows = self._branch_filter(self.alerts, branch)
        if severity:
            rows = [row for row in rows if row.get("severity") == severity.upper()]
        rows = self._date_filter(rows, start, end)

        # Apply any in-memory acknowledgement overrides.
        for row in rows:
            alert_id = row.get("alert_id")
            if isinstance(alert_id, int) and alert_id in self.alert_status_overrides:
                row.update(self.alert_status_overrides[alert_id])

        return {
            "branch": branch,
            "start": start,
            "end": end,
            "severity": severity,
            "total": len(rows),
            "data": rows,
        }

    def get_accounts(self, params: dict[str, list[str]]) -> dict[str, Any]:
        account_type = ((params.get("account_type") or [""])[0] or "").upper() or None
        name_query = ((params.get("name") or [""])[0] or "").casefold()

        rows = list(self.account_summary)
        if account_type:
            rows = [row for row in rows if row.get("account_type") == account_type]
        if name_query:
            rows = [row for row in rows if name_query in row.get("account_name", "").casefold()]

        return {
            "account_type": account_type,
            "name": name_query or None,
            "total": len(rows),
            "data": rows,
        }

    def get_duplicates(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None
        severity = ((params.get("severity") or [""])[0] or "").upper() or None
        duplicate_type = ((params.get("duplicate_type") or [""])[0] or "").upper() or None
        page = self._parse_int((params.get("page") or [None])[0], 1)
        per_page = self._parse_int((params.get("per_page") or [None])[0], 100)
        per_page = max(1, min(per_page, 1000))
        page = max(1, page)

        rows = list(self.duplicate_alerts)
        if branch:
            rows = [row for row in rows if row.get("branch") == branch]
        if severity:
            rows = [row for row in rows if row.get("severity") == severity]
        if duplicate_type:
            rows = [row for row in rows if row.get("duplicate_type") == duplicate_type]

        start_dt = self._parse_date(start)
        end_dt = self._parse_date(end)
        if start_dt or end_dt:
            filtered: list[dict[str, Any]] = []
            for row in rows:
                row_dt = self._parse_date(row.get("date_left") or row.get("date") or "")
                if row_dt is None:
                    continue
                if start_dt and row_dt < start_dt:
                    continue
                if end_dt and row_dt > end_dt:
                    continue
                filtered.append(row)
            rows = filtered

        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        page_rows = rows[start_index : start_index + per_page]
        return {
            "branch": branch,
            "start": start,
            "end": end,
            "severity": severity,
            "duplicate_type": duplicate_type,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "data": page_rows,
        }

    def get_vendor_concentration(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        start = (params.get("start") or [""])[0] or None
        end = (params.get("end") or [""])[0] or None
        severity = ((params.get("severity") or [""])[0] or "").upper() or None
        counterparty = ((params.get("counterparty") or [""])[0] or "").casefold()
        debit_account = ((params.get("debit_account") or [""])[0] or "").casefold()
        page = self._parse_int((params.get("page") or [None])[0], 1)
        per_page = self._parse_int((params.get("per_page") or [None])[0], 100)
        per_page = max(1, min(per_page, 1000))
        page = max(1, page)

        rows = list(self.vendor_concentration.get("anomalies", []))
        if branch:
            rows = [row for row in rows if row.get("branch") == branch]
        if severity:
            rows = [row for row in rows if row.get("severity") == severity]
        if counterparty:
            rows = [row for row in rows if counterparty in str(row.get("counterparty", "")).casefold()]
        if debit_account:
            rows = [row for row in rows if debit_account in str(row.get("debit_account", "")).casefold()]

        start_dt = self._parse_date(start)
        end_dt = self._parse_date(end)
        if start_dt or end_dt:
            filtered: list[dict[str, Any]] = []
            for row in rows:
                period_dt = self._parse_period(row.get("period"))
                if period_dt is None:
                    continue
                if start_dt and period_dt < start_dt:
                    continue
                if end_dt and period_dt > end_dt:
                    continue
                filtered.append(row)
            rows = filtered

        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        page_rows = rows[start_index : start_index + per_page]
        return {
            "branch": branch,
            "start": start,
            "end": end,
            "severity": severity,
            "counterparty": counterparty or None,
            "debit_account": debit_account or None,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "meta": self.vendor_concentration.get("meta", {}),
            "data": page_rows,
        }

    def get_benford(self, params: dict[str, list[str]]) -> dict[str, Any]:
        severity = ((params.get("severity") or [""])[0] or "").upper() or None
        dimension = (params.get("dimension") or [""])[0] or None
        group_key = ((params.get("group_key") or [""])[0] or "").casefold()
        flagged_only = self._parse_bool((params.get("flagged_only") or ["true"])[0], True)
        page = self._parse_int((params.get("page") or [None])[0], 1)
        per_page = self._parse_int((params.get("per_page") or [None])[0], 100)
        per_page = max(1, min(per_page, 1000))
        page = max(1, page)

        rows = list(self.benford_analysis.get("flagged_groups" if flagged_only else "all_groups", []))
        if severity:
            rows = [row for row in rows if row.get("severity") == severity]
        if dimension:
            rows = [row for row in rows if row.get("dimension") == dimension]
        if group_key:
            rows = [row for row in rows if group_key in str(row.get("group_key", "")).casefold()]

        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        page_rows = rows[start_index : start_index + per_page]
        return {
            "severity": severity,
            "dimension": dimension,
            "group_key": group_key or None,
            "flagged_only": flagged_only,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "meta": self.benford_analysis.get("meta", {}),
            "data": page_rows,
        }

    def get_round_clustering(self, params: dict[str, list[str]]) -> dict[str, Any]:
        branch = (params.get("branch") or [""])[0] or None
        severity = ((params.get("severity") or [""])[0] or "").upper() or None
        counterparty = ((params.get("counterparty") or [""])[0] or "").casefold()
        debit_account = ((params.get("debit_account") or [""])[0] or "").casefold()
        flagged_only = self._parse_bool((params.get("flagged_only") or ["true"])[0], True)
        page = self._parse_int((params.get("page") or [None])[0], 1)
        per_page = self._parse_int((params.get("per_page") or [None])[0], 100)
        per_page = max(1, min(per_page, 1000))
        page = max(1, page)

        rows = list(self.round_clustering.get("alerts" if flagged_only else "groups", []))
        if branch:
            rows = [row for row in rows if row.get("branch") == branch]
        if severity:
            rows = [row for row in rows if row.get("severity") == severity]
        if counterparty:
            rows = [row for row in rows if counterparty in str(row.get("counterparty", "")).casefold()]
        if debit_account:
            rows = [row for row in rows if debit_account in str(row.get("debit_account", "")).casefold()]

        total = len(rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start_index = (page - 1) * per_page
        page_rows = rows[start_index : start_index + per_page]
        return {
            "branch": branch,
            "severity": severity,
            "counterparty": counterparty or None,
            "debit_account": debit_account or None,
            "flagged_only": flagged_only,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "meta": self.round_clustering.get("meta", {}),
            "data": page_rows,
        }

    def acknowledge_alert(self, alert_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        note = str(payload.get("note", "")).strip()
        user_id = str(payload.get("user_id", "")).strip()
        self.alert_status_overrides[alert_id] = {
            "status": "ACKNOWLEDGED",
            "acknowledged_by": user_id,
            "acknowledged_note": note,
            "acknowledged_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        return {"alert_id": alert_id, **self.alert_status_overrides[alert_id]}

    def get_alert_by_id(self, alert_id: int) -> dict[str, Any] | None:
        for alert in self.alerts:
            if alert.get("alert_id") == alert_id:
                return alert
        return None


class MediciAPIHandler(BaseHTTPRequestHandler):
    store: ServingStore | None = None
    BRANCH_SCOPED_GET_ROUTES = {
        "/api/transactions",
        "/api/kpis",
        "/api/cashflow",
        "/api/alerts",
        "/api/duplicates",
        "/api/vendor-concentration",
        "/api/round-clustering",
        "/api/loans",
        "/api/expenses",
    }
    BRANCH_MANAGER_DENIED_GET_ROUTES = {
        "/api/accounts",
        "/api/benford",
    }

    @staticmethod
    def _first_param(params: dict[str, list[str]], key: str) -> str:
        return (params.get(key) or [""])[0].strip()

    def _resolve_request_role(self, params: dict[str, list[str]]) -> str:
        role = self._first_param(params, "role") or self.headers.get("X-Medici-Role", "")
        normalized = role.strip().upper().replace("-", "_").replace(" ", "_")
        if normalized in {"BRANCH_MANAGER", "MANAGER"}:
            return "BRANCH_MANAGER"
        return "SENIOR_BANK_OFFICIAL"

    def _resolve_assigned_branch(self, params: dict[str, list[str]]) -> str:
        return self._first_param(params, "assigned_branch") or self.headers.get("X-Medici-Assigned-Branch", "").strip()

    def _authorize_get_request(self, path: str, params: dict[str, list[str]]) -> tuple[bool, str | None]:
        role = self._resolve_request_role(params)
        if role != "BRANCH_MANAGER":
            return True, None

        if path in self.BRANCH_MANAGER_DENIED_GET_ROUTES:
            return False, "route is not available for branch manager role"

        if path not in self.BRANCH_SCOPED_GET_ROUTES:
            return True, None

        assigned_branch = self._resolve_assigned_branch(params)
        if not assigned_branch:
            return False, "assigned_branch is required for branch manager role"

        requested_branch = self._first_param(params, "branch")
        if requested_branch and requested_branch != assigned_branch:
            return False, "branch managers may only access their assigned branch"

        # Force branch-scoped queries to the assigned branch.
        params["branch"] = [assigned_branch]
        return True, None

    def _authorize_alert_acknowledge(self, alert_id: int, params: dict[str, list[str]]) -> tuple[bool, str | None]:
        role = self._resolve_request_role(params)
        if role != "BRANCH_MANAGER":
            return True, None

        assigned_branch = self._resolve_assigned_branch(params)
        if not assigned_branch:
            return False, "assigned_branch is required for branch manager role"

        store = self.store
        if store is None:
            return False, "server not initialized"

        alert = store.get_alert_by_id(alert_id)
        if alert is None:
            return False, "alert not found"

        if alert.get("branch") != assigned_branch:
            return False, "branch managers may only acknowledge alerts in their assigned branch"

        return True, None

    def _send_json(self, status_code: int, payload: Any) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    _ENDPOINTS = [
        {"method": "GET",  "path": "/health",                        "description": "Health check"},
        {"method": "GET",  "path": "/api",                           "description": "API endpoint index"},
        {"method": "GET",  "path": "/api/transactions",              "description": "Paginated transaction ledger",   "params": "branch, start, end, type, page, per_page"},
        {"method": "GET",  "path": "/api/kpis",                      "description": "Branch KPI summary",             "params": "branch, start, end"},
        {"method": "GET",  "path": "/api/accounts",                  "description": "Account balances",              "params": "account_type, name"},
        {"method": "GET",  "path": "/api/cashflow",                  "description": "Cash flow time series",          "params": "branch, start, end, granularity"},
        {"method": "GET",  "path": "/api/alerts",                    "description": "Anomaly and fraud alerts",       "params": "branch, start, end, severity"},
        {"method": "GET",  "path": "/api/duplicates",                "description": "Duplicate transaction alerts",   "params": "branch, start, end, severity, duplicate_type, page, per_page"},
        {"method": "GET",  "path": "/api/vendor-concentration",       "description": "Vendor concentration anomalies", "params": "branch, start, end, severity, counterparty, debit_account, page, per_page"},
        {"method": "GET",  "path": "/api/benford",                   "description": "Benford anomaly groups",         "params": "severity, dimension, group_key, flagged_only, page, per_page"},
        {"method": "GET",  "path": "/api/round-clustering",          "description": "Round-number clustering",        "params": "branch, severity, counterparty, debit_account, flagged_only, page, per_page"},
        {"method": "POST", "path": "/api/alerts/{id}/acknowledge",   "description": "Acknowledge an alert",          "body": "user_id, note"},
        {"method": "GET",  "path": "/api/loans",                     "description": "Open loan portfolio",           "params": "branch, status"},
        {"method": "GET",  "path": "/api/expenses",                  "description": "Expense breakdown",             "params": "branch, start, end"},
    ]

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        store = self.store
        if store is None:
            self._send_json(500, {"error": "server not initialized"})
            return

        is_allowed, reason = self._authorize_get_request(parsed.path, params)
        if not is_allowed:
            self._send_json(403, {"error": reason})
            return

        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "service": "medici-api"})
            return
        if parsed.path in {"/api", "/api/"}:
            self._send_json(200, {"service": "medici-api", "endpoints": self._ENDPOINTS})
            return
        if parsed.path == "/api/transactions":
            self._send_json(200, store.get_transactions(params))
            return
        if parsed.path == "/api/kpis":
            self._send_json(200, store.get_kpis(params))
            return
        if parsed.path == "/api/accounts":
            self._send_json(200, store.get_accounts(params))
            return
        if parsed.path == "/api/cashflow":
            self._send_json(200, store.get_cashflow(params))
            return
        if parsed.path == "/api/alerts":
            self._send_json(200, store.get_alerts(params))
            return
        if parsed.path == "/api/duplicates":
            self._send_json(200, store.get_duplicates(params))
            return
        if parsed.path == "/api/vendor-concentration":
            self._send_json(200, store.get_vendor_concentration(params))
            return
        if parsed.path == "/api/benford":
            self._send_json(200, store.get_benford(params))
            return
        if parsed.path == "/api/round-clustering":
            self._send_json(200, store.get_round_clustering(params))
            return
        if parsed.path == "/api/loans":
            self._send_json(200, store.get_loans(params))
            return
        if parsed.path == "/api/expenses":
            self._send_json(200, store.get_expenses(params))
            return

        self._send_json(404, {"error": f"unknown endpoint: {parsed.path}"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        store = self.store
        if store is None:
            self._send_json(500, {"error": "server not initialized"})
            return

        if parsed.path.startswith("/api/alerts/") and parsed.path.endswith("/acknowledge"):
            parts = parsed.path.strip("/").split("/")
            try:
                alert_id = int(parts[2])
            except (IndexError, ValueError):
                self._send_json(400, {"error": "invalid alert id"})
                return
            is_allowed, reason = self._authorize_alert_acknowledge(alert_id, params)
            if not is_allowed:
                self._send_json(403, {"error": reason})
                return
            payload = self._read_body()
            self._send_json(200, store.acknowledge_alert(alert_id, payload))
            return

        self._send_json(404, {"error": f"unknown endpoint: {parsed.path}"})

    def log_message(self, fmt: str, *args: Any) -> None:
        method = self.command if hasattr(self, "command") else "-"
        print(f"{self.address_string()} {method} {self.path} {args[1] if len(args) > 1 else ''}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Medici serving-layer HTTP API")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument(
        "--serving-dir",
        default=str(SERVING_DIR),
        help="Path to the serving output directory",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    serving_dir = Path(args.serving_dir)
    api_dir = serving_dir / "api"
    store = ServingStore(serving_dir, api_dir)
    MediciAPIHandler.store = store

    server = ThreadingHTTPServer((args.host, args.port), MediciAPIHandler)
    print(f"Medici API server listening on http://{args.host}:{args.port}")
    print(f"Serving directory: {serving_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
