"""Conservative and privacy-limited enterprise resource policy checks.

This module is a sidecar to access-review prioritization, NOT an EDR or a web
browsing monitor. Only vetted managed business assets with explicit, active
and company-approved policy mappings may generate review findings. Unknown
resources, missing policy, personal/media sites, and failed access attempts
cannot be promoted into a violation by anomaly detection.
"""
from __future__ import annotations
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models import (Account, Employee, EmployeeTransfer, GovernedResourcePolicy, GovernedResourceUse)

SUPPORTED_KINDS = {'business_application', 'managed_software', 'managed_web_app'}


def _norm(value):
    return str(value or '').strip().casefold()


def _violation(employee, policy):
    """Require an explicit mismatch, never infer a deny from missing metadata."""
    if employee is None:
        return False
    dept_policy = {_norm(v) for v in (policy.allowed_departments or []) if _norm(v)}
    role_policy = {_norm(v) for v in (policy.allowed_job_titles or []) if _norm(v)}
    if not dept_policy and not role_policy:
        return False
    # Rules mean an employee is authorized if the configured dimensions match.
    # Missing employee attribute yields insufficient evidence, not a violation.
    if dept_policy and not _norm(employee.department):
        return False
    if role_policy and not _norm(employee.job_title):
        return False
    return ((bool(dept_policy) and _norm(employee.department) not in dept_policy) or
            (bool(role_policy) and _norm(employee.job_title) not in role_policy))


def summarize_governed_resources(db: Session, *, since, as_of, organization_key='demo'):
    """One summary per account: do not include private browsing or event text.

    A single approved policy per (platform,kind,key) is chosen as of review time.
    A v1 policy change is not assumed to describe authorization *at event time*:
    findings are only potential CURRENT access mismatch, not past wrongdoing.
    """
    policies = db.query(GovernedResourcePolicy).filter(
        GovernedResourcePolicy.organization_key == organization_key,
        GovernedResourcePolicy.active.is_(True),
        GovernedResourcePolicy.effective_at <= as_of).order_by(
        GovernedResourcePolicy.effective_at, GovernedResourcePolicy.id).all()
    indexed = {}
    for p in policies:
        if p.resource_kind in SUPPORTED_KINDS and p.approved_by and p.policy_version:
            indexed[(p.platform,p.resource_kind,p.resource_key)] = p
    if not indexed:
        return {}
    # Bounded per-account summaries could move to database aggregate tables at scale.
    events = db.query(GovernedResourceUse, Account, Employee).join(
        Account, GovernedResourceUse.account_id == Account.id).outerjoin(
        Employee, Account.employee_id == Employee.id).filter(
        GovernedResourceUse.occurred_at >= since,
        GovernedResourceUse.occurred_at <= as_of,
        GovernedResourceUse.source_verified.is_(True),
        GovernedResourceUse.outcome == 'observed',
        GovernedResourceUse.resource_kind.in_(SUPPORTED_KINDS)).all()
    # Do not retroactively label pre-transfer use against the employee's NEW job.
    # A transfer itself is already an independent mandatory review trigger.
    latest_transfers = {}
    for emp_id, transfer_time in db.query(EmployeeTransfer.employee_id, EmployeeTransfer.occurred_at).filter(
            EmployeeTransfer.occurred_at <= as_of).all():
        if emp_id not in latest_transfers or transfer_time > latest_transfers[emp_id]:
            latest_transfers[emp_id] = transfer_time
    found = defaultdict(lambda: {'managed_policy_conflict_count': 0,
                                 'managed_policy_conflict_resources': []})
    seen = set()
    for event, account, employee in events:
        key = (account.platform,event.resource_kind,event.resource_key)
        policy = indexed.get(key)
        if policy is None or not _violation(employee,policy):
            continue
        if event.occurred_at < policy.effective_at:
            continue  # never retroactively apply a newer rule
        if employee is not None and event.occurred_at < latest_transfers.get(employee.id, event.occurred_at):
            continue  # activity preceded employee's current reporting scope
        identity = (account.id,event.resource_kind,event.resource_key)
        if identity in seen:
            continue
        seen.add(identity)
        found[account.id]['managed_policy_conflict_count'] += 1
        # Resource identifier only, not raw URL/browser data, or user content.
        found[account.id]['managed_policy_conflict_resources'].append({
            'resource_kind':event.resource_kind,
            'resource_key':event.resource_key,
            'policy_version':policy.policy_version,
            'reason':'Current department/job scope differs from organization-approved access policy',
        })
    return dict(found)
