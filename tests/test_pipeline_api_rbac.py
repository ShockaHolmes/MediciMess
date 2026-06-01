"""Authorization tests for branch-scoped API access rules."""

from pipeline_api_server import MediciAPIHandler


class DummyStore:
    def __init__(self, alert_branch: str = "Florence"):
        self._alert_branch = alert_branch

    def get_alert_by_id(self, alert_id: int):
        return {"alert_id": alert_id, "branch": self._alert_branch}


def _make_handler(headers=None, store=None):
    handler = object.__new__(MediciAPIHandler)
    handler.headers = headers or {}
    handler.store = store
    return handler


def test_senior_role_has_no_branch_restriction_for_scoped_route():
    handler = _make_handler()
    params = {"branch": ["Rome"]}

    allowed, reason = handler._authorize_get_request("/api/kpis", params)

    assert allowed is True
    assert reason is None
    assert params["branch"] == ["Rome"]


def test_branch_manager_defaults_branch_to_assigned_scope():
    handler = _make_handler()
    params = {
        "role": ["branch_manager"],
        "assigned_branch": ["Florence"],
    }

    allowed, reason = handler._authorize_get_request("/api/kpis", params)

    assert allowed is True
    assert reason is None
    assert params["branch"] == ["Florence"]


def test_branch_manager_cannot_request_other_branch():
    handler = _make_handler()
    params = {
        "role": ["branch_manager"],
        "assigned_branch": ["Florence"],
        "branch": ["Rome"],
    }

    allowed, reason = handler._authorize_get_request("/api/transactions", params)

    assert allowed is False
    assert reason == "branch managers may only access their assigned branch"


def test_branch_manager_cannot_access_non_scoped_global_routes():
    handler = _make_handler()
    params = {
        "role": ["branch_manager"],
        "assigned_branch": ["Florence"],
    }

    allowed, reason = handler._authorize_get_request("/api/accounts", params)

    assert allowed is False
    assert reason == "route is not available for branch manager role"


def test_branch_manager_acknowledge_requires_same_branch_alert():
    handler = _make_handler(store=DummyStore(alert_branch="Rome"))
    params = {
        "role": ["branch_manager"],
        "assigned_branch": ["Florence"],
    }

    allowed, reason = handler._authorize_alert_acknowledge(42, params)

    assert allowed is False
    assert reason == "branch managers may only acknowledge alerts in their assigned branch"
