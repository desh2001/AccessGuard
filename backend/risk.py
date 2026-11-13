"""Enhanced AccessGuard risk engine — explainable, rule-based baseline.

NOT a trained ML model. All factors are deterministic and documented.
Absence of activity logs is NEVER treated as proof that access is unused.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


# Risk factor weights (must sum to ≤100 starting from base of 10)
_WEIGHTS = {
    'unlinked_account': 40,      # Orphaned — owner unknown
    'departed_identity': 50,     # Leaver still holding access
    'admin_privilege': 23,       # Privileged admin role
    'cross_department': 23,      # Permission outside expected dept
    'long_inactivity_90d': 23,   # No verified use ≥ 90 days (if logs exist)
    'moderate_inactivity_45d': 9, # No verified use 45–89 days
    'missing_use_evidence': 0,   # Note only — not scored (evidence gap)
}


def calculate_risk(record: dict) -> tuple[int, list[str]]:
    """Return (risk_score 0–100, list[explanation_strings]).

    Scoring is additive from a base of 10, capped at 100.
    Each factor is independently explainable.
    """
    score = 10
    reasons: list[str] = []

    # Factor 1: Unlinked / orphaned account
    if record.get('identity_id') is None:
        score += _WEIGHTS['unlinked_account']
        reasons.append('Unlinked technical account — owner identity not verified')

    # Factor 2: Departed employee still holding access
    elif record.get('status') == 'Departed':
        score += _WEIGHTS['departed_identity']
        reasons.append('Departed identity still holds active access')

    # Factor 3: Admin / privileged permission
    if record.get('privilege'):
        score += _WEIGHTS['admin_privilege']
        reasons.append('Privileged administrator permission detected')

    # Factor 4: Cross-department access (Finance in Dev/Infra, etc.)
    if record.get('cross_department'):
        score += _WEIGHTS['cross_department']
        reasons.append('Permission outside expected department boundary')

    # Factor 5 / 6: Last verified use analysis
    last = parse_time(record.get('last_verified_use'))
    if last is None:
        # Missing log evidence is noted but NOT scored — cannot prove non-use
        reasons.append('Use evidence unavailable — absence of logs does NOT prove access is unused')
    else:
        days = max(0, (datetime.now(timezone.utc) - last).days)
        if days >= 90:
            score += _WEIGHTS['long_inactivity_90d']
            reasons.append(
                f'No verified use for {days} days (requires adequate log coverage to interpret)'
            )
        elif days >= 45:
            score += _WEIGHTS['moderate_inactivity_45d']
            reasons.append(f'Last verified use was {days} days ago')

    return min(score, 100), reasons


def risk_level(score: int) -> str:
    if score >= 85:
        return 'Critical'
    if score >= 60:
        return 'High'
    if score >= 35:
        return 'Medium'
    return 'Low'


def access_dict(grant, account, identity, system) -> dict:
    """Build a full access-grant dict with risk scores and explanations."""
    record = {
        'id': grant.id,
        'account_id': account.id,
        'identity_id': account.identity_id,
        'system_id': system.id,
        'permission': grant.permission,
        'resource': grant.resource,
        'privilege': grant.privilege,
        'cross_department': grant.cross_department,
        'last_verified_use': (
            grant.last_verified_use.isoformat() if grant.last_verified_use else None
        ),
        'grant_status': grant.status,
        'identity_name': identity.name if identity else '[Unlinked account]',
        'email': identity.email if identity else account.account_email,
        'department': identity.department if identity else 'Unmapped',
        'status': identity.status if identity else 'Unmapped',
        'type': identity.type if identity else 'Unknown',
        'system_name': system.name,
        'system_category': system.category,
        'account_username': account.username,
    }
    score, reasons = calculate_risk(record)
    record['risk_score'] = score
    record['risk_level'] = risk_level(score)
    record['reasons'] = reasons
    return record
