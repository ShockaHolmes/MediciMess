"""Lightweight HTTP API for the Medici data serving layer.

This server reads precomputed serving-layer outputs from data/serving and exposes
REST endpoints for the dashboard and reports.

Endpoints:
- GET /health
- GET /api/kpis?branch=&start=&end=
- GET /api/transactions?branch=&start=&end=&type=&page=&per_page=
- GET /api/cashflow?branch=&start=&end=&granularity=
- GET /api/loans?branch=&status=
- GET /api/expenses?branch=&start=&end=
- GET /api/alerts?branch=&start=&end=&severity=
- POST /api/alerts/{id}/acknowledge
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
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


class MediciAPIHandler(BaseHTTPRequestHandler):
    store: ServingStore | None = None

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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        store = self.store
        if store is None:
            self._send_json(500, {"error": "server not initialized"})
            return

        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "service": "medici-api"})
            return
        if parsed.path == "/api/kpis":
            self._send_json(200, store.get_kpis(params))
            return
        if parsed.path == "/api/transactions":
            self._send_json(200, store.get_transactions(params))
            return
        if parsed.path == "/api/cashflow":
            self._send_json(200, store.get_cashflow(params))
            return
        if parsed.path == "/api/loans":
            self._send_json(200, store.get_loans(params))
            return
        if parsed.path == "/api/expenses":
            self._send_json(200, store.get_expenses(params))
            return
        if parsed.path == "/api/alerts":
            self._send_json(200, store.get_alerts(params))
            return

        self._send_json(404, {"error": f"unknown endpoint: {parsed.path}"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
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
            payload = self._read_body()
            self._send_json(200, store.acknowledge_alert(alert_id, payload))
            return

        self._send_json(404, {"error": f"unknown endpoint: {parsed.path}"})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep terminal output concise during dashboard/API development.
        return


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
