"""Versioned, privacy-minimized features shared by training and inference.

No names, usernames, emails, raw activity events, or employee IDs are model inputs.
Missing resource-use evidence is explicitly not treated as inactivity.
"""
from datetime import datetime

FEATURE_SCHEMA_VERSION = "1.0"
CATEGORICAL = ["department", "platform", "permission_class", "sensitivity", "employee_status", "account_status"]
NUMERIC = ["unmapped", "outside_role", "resource_use_observed", "last_used_days", "last_login_observed", "last_login_days"]
FEATURE_COLUMNS = CATEGORICAL + NUMERIC

PRIVILEGED = {"admin", "owner", "root", "sysadmin", "write_all", "maintain"}
EXPECTED_ACCESS = {
    "Finance": {"finance", "erp", "billing", "payroll", "shared"},
    "Engineering": {"github", "dev", "staging", "linux", "ci", "shared"},
    "HR": {"hr", "people", "payroll", "shared"},
    "Sales": {"crm", "sales", "shared"},
    "IT": {"github", "linux", "windows", "active directory", "dev", "staging", "shared", "production", "admin"},
}


def outside_role(department: str | None, resource: str) -> bool:
    """Demo-only departmental access policy, not a generalized authorization rule."""
    if not department or department not in EXPECTED_ACCESS:
        return False  # Unknown policy is not automatically a policy breach
    return not any(token in resource.lower() for token in EXPECTED_ACCESS[department])


def permission_class(value: str) -> str:
    p = (value or "").lower()
    if p in PRIVILEGED:
        return "privileged"
    if p in {"write", "edit", "contribute", "push"}:
        return "write"
    if p in {"read", "view", "pull"}:
        return "read"
    return "other"


def age_days(time: datetime | None, now: datetime) -> float:
    if time is None:
        return 0.0  # A separate observed flag distinguishes missing values
    return float(min(365, max(0, (now - time).days)))


def entitlement_features(entitlement, now: datetime) -> dict:
    account = entitlement.account
    employee = account.employee
    return {
        "department": employee.department if employee else "Unknown",
        "platform": account.platform or "Unknown",
        "permission_class": permission_class(entitlement.permission),
        "sensitivity": (entitlement.sensitivity or "medium").lower(),
        "employee_status": employee.status.lower() if employee else "unknown",
        "account_status": (account.status or "unknown").lower(),
        "unmapped": int(employee is None),
        "outside_role": int(outside_role(employee.department, entitlement.resource)) if employee else 0,
        "resource_use_observed": int(entitlement.last_used_at is not None),
        "last_used_days": age_days(entitlement.last_used_at, now),
        "last_login_observed": int(account.last_login is not None),
        "last_login_days": age_days(account.last_login, now),
    }
