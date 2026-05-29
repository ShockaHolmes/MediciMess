# Branch Operations Dashboard RBAC Specification (Phase 4)

## 1. Purpose

This specification defines role-based access control (RBAC) for the Branch Operations Dashboard.

Scope includes:
1. Dashboard access permissions
2. Report access permissions
3. Anomaly alert access permissions

## 2. Roles

### 2.1 Senior Bank Official

Business intent:
Global oversight of operations, risk, and fraud outcomes across all branches.

Role code:
SENIOR_BANK_OFFICIAL

### 2.2 Branch Manager

Business intent:
Operational management for a single assigned branch.

Role code:
BRANCH_MANAGER

### 2.3 Auditor

Business intent:
Independent audit and forensic review, with evidence access needed for investigations.

Role code:
AUDITOR

### 2.4 Read-Only Student

Business intent:
Educational access for training exercises without administrative or workflow actions.

Role code:
READ_ONLY_STUDENT

## 3. Permission Model

Permission levels:
1. None: no access
2. View Assigned: view only assigned-branch data
3. View All: view all branches
4. Act: can perform workflow actions such as acknowledge, comment, assign, or export privileged packets
5. Admin: can configure thresholds, role mappings, and access policies

Data-scope rules:
1. Assigned branch scope applies to BRANCH_MANAGER by default.
2. AUDITOR and SENIOR_BANK_OFFICIAL have cross-branch scope.
3. READ_ONLY_STUDENT is restricted to training datasets and non-production workspaces.

## 4. Dashboard Access Permissions

| Dashboard Capability | Senior Bank Official | Branch Manager | Auditor | Read-Only Student |
|---|---|---|---|---|
| Open dashboard application | View All | View Assigned | View All | View Assigned (training only) |
| View branch KPI tiles | View All | View Assigned | View All | View Assigned |
| View branch comparison panels | View All | None | View All | None |
| View transaction drill-down table | View All | View Assigned | View All | View Assigned (masked counterparty) |
| View account balances panel | View All | View Assigned | View All | View Assigned |
| View loan/expense trend panels | View All | View Assigned | View All | View Assigned |
| Configure dashboard filters and saved views | Act | Act | Act | None |
| Change global dashboard defaults | Admin | None | None | None |

## 5. Report Access Permissions

| Report Capability | Senior Bank Official | Branch Manager | Auditor | Read-Only Student |
|---|---|---|---|---|
| View standard branch reports | View All | View Assigned | View All | View Assigned |
| View forensic/anomaly reports | View All | View Assigned (summary only) | View All | View Assigned (summary only) |
| View report-level transaction evidence | View All | View Assigned | View All | None |
| Export CSV/JSON reports | Act | Act (assigned branch only) | Act | None |
| Export cross-branch executive package | Act | None | Act | None |
| Schedule recurring report jobs | Admin | None | None | None |

## 6. Anomaly Alert Access Permissions

| Anomaly Alert Capability | Senior Bank Official | Branch Manager | Auditor | Read-Only Student |
|---|---|---|---|---|
| View anomaly alert queue | View All | View Assigned | View All | View Assigned (training only) |
| View alert details and evidence links | View All | View Assigned | View All | View Assigned (masked evidence) |
| Acknowledge alert | Act | Act (assigned branch only) | Act | None |
| Assign alert owner | Act | Act (assigned branch only) | Act | None |
| Add investigation notes | Act | Act | Act | None |
| Reopen or close alert | Act | Act (assigned branch only) | Act | None |
| Override detection threshold outcome | Admin | None | None | None |
| Edit anomaly rule configuration | Admin | None | None | None |

## 7. Data Protection Constraints

1. Counterparty and free-text description fields are masked for READ_ONLY_STUDENT in production-derived datasets.
2. READ_ONLY_STUDENT cannot access instructor-only guides or answer-key assets.
3. Sensitive exports are watermark-stamped with user, role, and timestamp.
4. All alert actions are immutable-audited with actor role and before/after state.

## 8. Enforcement Requirements

1. API endpoints must enforce role and data-scope checks server-side.
2. UI component visibility is not sufficient for security and must mirror backend authorization.
3. Endpoint responses must return 403 for unauthorized access attempts.
4. Authorization policy should be centrally defined and unit-tested for each role-capability pair.

## 9. Minimum Test Matrix

1. SENIOR_BANK_OFFICIAL can read and act across all branches and configure policy endpoints.
2. BRANCH_MANAGER cannot access cross-branch dashboards or executive report exports.
3. AUDITOR can review and act on alerts across branches but cannot edit rule configuration.
4. READ_ONLY_STUDENT cannot acknowledge alerts, export privileged reports, or access unmasked evidence.

## 10. API Route Authorization Mapping

This section maps current dashboard API routes to role permissions for implementation in the backend authorization layer.

Legend:
1. Allow All: cross-branch access
2. Allow Assigned: only assigned branch data
3. Deny: no access
4. Allow Assigned (Masked): assigned branch only with counterparty/details masking

| Route | Senior Bank Official | Branch Manager | Auditor | Read-Only Student | Enforcement Notes |
|---|---|---|---|---|---|
| GET /health | Allow All | Allow All | Allow All | Allow All | Health endpoint is non-sensitive. |
| GET /api | Allow All | Allow All | Allow All | Allow All | Route index may be public but should not leak hidden admin routes. |
| GET /api/transactions | Allow All | Allow Assigned | Allow All | Allow Assigned (Masked) | Enforce branch scoping server-side even if branch query param is omitted. |
| GET /api/kpis | Allow All | Allow Assigned | Allow All | Allow Assigned | Students can view aggregate KPIs only in training scope. |
| GET /api/accounts | Allow All | Allow Assigned | Allow All | Allow Assigned | Student role should not see sensitive counterparty-linked derived fields if added later. |
| GET /api/cashflow | Allow All | Allow Assigned | Allow All | Allow Assigned | Restrict cross-branch cashflow to non-student roles. |
| GET /api/expenses | Allow All | Allow Assigned | Allow All | Allow Assigned (Masked) | Mask vendor names/details for student role in production-derived datasets. |
| GET /api/loans | Allow All | Allow Assigned | Allow All | Allow Assigned | If borrower-level details are added later, apply masking to student role. |
| GET /api/alerts | Allow All | Allow Assigned | Allow All | Allow Assigned (Masked) | Student role can view summaries only; no full evidence payload. |
| POST /api/alerts/{id}/acknowledge | Allow All | Allow Assigned | Allow All | Deny | Branch Manager can act only on assigned branch alerts. |
| GET /api/duplicates | Allow All | Allow Assigned | Allow All | Allow Assigned (Masked) | Student role cannot view full description fields in evidence records. |
| GET /api/vendor-concentration | Allow All | Allow Assigned | Allow All | Allow Assigned (Masked) | Student role should receive redacted counterparty in non-training environments. |
| GET /api/benford | Allow All | Allow Assigned | Allow All | Allow Assigned | Benford group summaries are generally safe at aggregate level. |
| GET /api/round-clustering | Allow All | Allow Assigned | Allow All | Allow Assigned | For student role, enforce training-scope dataset only. |

Implementation notes:
1. Authorization checks must execute before query filtering and pagination.
2. Branch-scoped roles must not bypass scope by omitting query params.
3. Masking logic should be centralized and role-aware to avoid endpoint drift.
4. All denied requests must return 403 with auditable metadata (role, route, timestamp).

## 11. Versioning

Document version: 1.1

Status: Phase 4 baseline RBAC policy with API route mapping for dashboard rollout
