"""Quarterly account-level features. No identifiers, emails or usernames in model inputs.

CRITICAL: Historical activity observations are not proof of complete log coverage.
Missing telemetry must never be converted into 'zero usage = unnecessary access'.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import joinedload
from sqlalchemy import case, func, or_, and_, exists

from app.models import Employee, Account, Activity, Entitlement, ActivityCoverage, DirectorySnapshot, ADGroupMembership, ADGroupMembershipHistory, EmployeeTransfer, ADGroupChange, ADGroupCatalog, TransferAccessDisposition, utcnow
from .features import PRIVILEGED, outside_role
from .governed_resources import summarize_governed_resources
from .platform_models import platform_key, PLATFORM_CONFIG

CATEGORICAL = ["platform", "department", "account_type", "permission_profile"]
NUMERIC = [
    "entitlement_count", "privileged_entitlements", "sensitive_entitlements",
    "outside_role_count", "successful_logins_window", "failed_logins_window",
    "resource_use_events_window", "active_days_window", "distinct_resources_used_window",
    "permission_changes_window", "use_age_days", "use_evidence_observed",
    "resource_uses_month_1", "resource_uses_month_2", "resource_uses_month_3",
    "log_coverage_days", "log_coverage_known",
    "ad_group_count", "privileged_ad_group_count", "ad_group_data_known",
    "group_changes_window", "transfers_window", "manager_changes_window",
    "department_changes_window", "org_unit_changes_window", "recent_transfer_flag", "days_since_last_transfer",
    "transfer_history_known", "ad_department_mismatch", "ad_reporting_known",
    # Catalog-driven, organization-scoped features: never one-hot raw AD group names.
    "mapped_access_ad_group_count", "non_access_ad_group_count",
    "unmapped_ad_group_count", "out_of_scope_ad_group_count",
    "group_catalog_coverage_fraction",
]
FEATURE_COLUMNS = CATEGORICAL + NUMERIC
FEATURE_SCHEMA_VERSION = "quarterly-2.1-governed-ad-transfer"

SUCCESS_LOGIN_EVENTS = {"login_success", "login", "ssh_login_success", "signin_success"}
FAILED_LOGIN_EVENTS = {"login_failed", "ssh_login_failed", "signin_failed"}
VERIFIED_USE_EVENTS = {"resource_use"}
PERMISSION_CHANGE_EVENTS = {"permission_changed", "privilege_change", "permission_change"}
SUPPORTED_EVENTS = SUCCESS_LOGIN_EVENTS | FAILED_LOGIN_EVENTS | VERIFIED_USE_EVENTS | PERMISSION_CHANGE_EVENTS


def aggregate_accounts(db, as_of: datetime | None = None, window_days: int = 90,
                       coverage_by_platform: dict[str, int] | None = None) -> list[dict]:
    """Return one record per account for a past window; no use/absence claims from missing logs.

    Event counts are aggregated in SQL. Directory-group lookups currently load a
    bounded snapshot; large production deployments need materialized per-tenant
    aggregates, partitioning and performance testing.
    """
    if not 30 <= window_days <= 365:
        raise ValueError("window_days must be from 30 to 365")
    as_of = as_of or utcnow()
    since = as_of - timedelta(days=window_days)
    coverage_by_platform = dict(coverage_by_platform or {})
    # Merge overlap in resource-use collection intervals; use full elapsed days,
    # not merely dates touched (a 1-minute interval must not count as one full day).
    coverage_records = db.query(ActivityCoverage).filter(
        ActivityCoverage.event_type.in_({'resource_use', 'windows_privileged_logon',
                                       'linux_sudo', 'github_repo_activity'}),
        ActivityCoverage.end_at > since, ActivityCoverage.start_at <= as_of).all()
    coverage_intervals = defaultdict(list)
    for item in coverage_records:
        coverage_intervals[(item.platform, item.event_type)].append((max(since, item.start_at), min(as_of, item.end_at)))
    signal_coverage_days = {}
    for (platform, event_type), intervals in coverage_intervals.items():
        elapsed = 0.0
        merged_end = None
        for start, end in sorted(intervals):
            if merged_end is None or start > merged_end:
                elapsed += (end - start).total_seconds()
                merged_end = end
            elif end > merged_end:
                elapsed += (end - merged_end).total_seconds()
                merged_end = end
        if event_type == 'resource_use':
            coverage_by_platform[platform] = min(window_days, elapsed / 86400)
        else:
            signal_coverage_days[(platform, event_type)] = min(window_days, elapsed / 86400)
    # AD context is attached to the employee, shared by their linked application accounts.
    # Complete historical group/transfer evidence must be attested; missing is NOT zero.
    snapshots = {x.employee_id: x for x in db.query(DirectorySnapshot).filter(
        DirectorySnapshot.snapshot_at <= as_of).all()}
    # Group names are organization-specific and are NOT model categories.
    # Only an approved, scoped catalog entry can classify an AD group as
    # access-bearing/privileged, and unmapped groups stay unresolved.
    # Latest known membership observation at or before the review timestamp.
    # A later sync must never rewrite the features of an earlier frozen cycle.
    last_observed = db.query(
        ADGroupMembershipHistory.employee_id.label('employee_id'),
        ADGroupMembershipHistory.organization_key.label('organization_key'),
        ADGroupMembershipHistory.directory_key.label('directory_key'),
        ADGroupMembershipHistory.group_key.label('group_key'),
        func.max(ADGroupMembershipHistory.observed_at).label('last_at'),
    ).filter(ADGroupMembershipHistory.observed_at <= as_of).group_by(
        ADGroupMembershipHistory.employee_id, ADGroupMembershipHistory.organization_key,
        ADGroupMembershipHistory.directory_key, ADGroupMembershipHistory.group_key).subquery()
    observations = db.query(ADGroupMembershipHistory, ADGroupCatalog).join(last_observed, and_(
        ADGroupMembershipHistory.employee_id == last_observed.c.employee_id,
        ADGroupMembershipHistory.organization_key == last_observed.c.organization_key,
        ADGroupMembershipHistory.directory_key == last_observed.c.directory_key,
        ADGroupMembershipHistory.group_key == last_observed.c.group_key,
        ADGroupMembershipHistory.observed_at == last_observed.c.last_at,
    )).outerjoin(ADGroupCatalog, and_(
        ADGroupCatalog.organization_key == ADGroupMembershipHistory.organization_key,
        ADGroupCatalog.directory_key == ADGroupMembershipHistory.directory_key,
        ADGroupCatalog.group_key == ADGroupMembershipHistory.group_key,
        ADGroupCatalog.effective_at <= as_of, ADGroupCatalog.updated_at <= as_of,
    )).filter(ADGroupMembershipHistory.active.is_(True)).all()
    # Legacy V5 rows are only a current snapshot; include them when they have
    # no history but do not fabricate earlier group membership states.
    covered_keys = {(m.employee_id, m.organization_key, m.directory_key, m.group_key)
                    for m, _ in observations}
    historical_keys = {tuple(row) for row in db.query(
        ADGroupMembershipHistory.employee_id, ADGroupMembershipHistory.organization_key,
        ADGroupMembershipHistory.directory_key, ADGroupMembershipHistory.group_key).distinct().all()}
    legacy_rows = db.query(ADGroupMembership, ADGroupCatalog).outerjoin(ADGroupCatalog, and_(
        ADGroupCatalog.organization_key == ADGroupMembership.organization_key,
        ADGroupCatalog.directory_key == ADGroupMembership.directory_key,
        ADGroupCatalog.group_key == ADGroupMembership.group_key,
        ADGroupCatalog.effective_at <= as_of, ADGroupCatalog.updated_at <= as_of,
    )).filter(ADGroupMembership.active.is_(True), ADGroupMembership.synced_at <= as_of).all()
    joined_groups = observations + [(m,d) for m,d in legacy_rows
                       if (m.employee_id,m.organization_key,m.directory_key,m.group_key) not in historical_keys]
    group_summary = defaultdict(lambda: dict(total=0, privileged=0, access=0, non_access=0,
                                              unknown=0, out_of_scope=0))
    employees_by_id = {e.id: e for e in db.query(Employee).all()}
    for membership, definition in joined_groups:
        counters = group_summary[membership.employee_id]
        counters['total'] += 1
        if definition is None or definition.access_relevance == 'unknown':
            counters['unknown'] += 1
            continue
        if definition.access_relevance == 'non_access':
            counters['non_access'] += 1
            continue
        counters['access'] += 1
        if definition.privilege_tier == 'privileged':
            counters['privileged'] += 1
        employee = employees_by_id.get(membership.employee_id)
        allowed = {x.strip().casefold() for x in (definition.allowed_departments or [])}
        if allowed and employee and employee.department.strip().casefold() not in allowed:
            counters['out_of_scope'] += 1

    group_changes = db.query(ADGroupChange.employee_id, func.count(ADGroupChange.id)).filter(
        ADGroupChange.occurred_at >= since, ADGroupChange.occurred_at <= as_of).group_by(ADGroupChange.employee_id).all()
    groups_changed_by_emp = {eid: int(n) for eid, n in group_changes}
    changed_department = (func.coalesce(EmployeeTransfer.from_department, '') !=
                          func.coalesce(EmployeeTransfer.to_department, ''))
    changed_manager = (func.coalesce(EmployeeTransfer.from_manager, '') !=
                       func.coalesce(EmployeeTransfer.to_manager, ''))
    changed_ou = (func.coalesce(EmployeeTransfer.from_org_unit, '') !=
                  func.coalesce(EmployeeTransfer.to_org_unit, ''))
    transfers = db.query(
        EmployeeTransfer.employee_id, func.count(EmployeeTransfer.id),
        func.sum(case((changed_manager, 1), else_=0)),
        func.sum(case((changed_department, 1), else_=0)),
        func.sum(case((changed_ou, 1), else_=0)),
        func.max(EmployeeTransfer.occurred_at),
    ).filter(EmployeeTransfer.occurred_at >= since, EmployeeTransfer.occurred_at <= as_of).group_by(EmployeeTransfer.employee_id).all()
    transfers_by_emp = {eid: (int(n), int(mc or 0), int(dc or 0), int(ouc or 0), last)
                        for eid, n, mc, dc, ouc, last in transfers}
    accounts = db.query(Account).options(joinedload(Account.employee), joinedload(Account.entitlements)).all()
    # A transfer creates an obligation PER currently active application account.
    # Older unresolved transfers remain mandatory until an actual reviewer decision.
    transfer_history = db.query(EmployeeTransfer.id, EmployeeTransfer.employee_id,
                                EmployeeTransfer.occurred_at).filter(
                                EmployeeTransfer.occurred_at <= as_of).all()
    transfer_by_employee = defaultdict(list)
    for transfer_id, employee_id, occurred_at in transfer_history:
        transfer_by_employee[employee_id].append((transfer_id, occurred_at))
    already_reviewed = {(rec.transfer_id, rec.account_id) for rec in db.query(
        TransferAccessDisposition.transfer_id, TransferAccessDisposition.account_id).filter(
        TransferAccessDisposition.reviewed_at <= as_of).all()}

    # Perform set-based aggregation in the database instead of loading all
    # 90-day raw events into Python (which can mean millions of events).
    period_third = window_days / 3.0
    cut1, cut2 = since + timedelta(days=period_third), since + timedelta(days=2 * period_third)
    event = func.lower(func.trim(Activity.event_type))
    success = event.in_(SUCCESS_LOGIN_EVENTS)
    failed = event.in_(FAILED_LOGIN_EVENTS)
    # Count only resource-use evidence attributable to an entitlement that is
    # still granted to this account, not unrelated historical resource activity.
    grant_match = exists().where(and_(
        Entitlement.account_id == Activity.account_id,
        Entitlement.resource == Activity.resource,
        Entitlement.active.is_(True),
    )).correlate(Activity)
    resource_used = event.in_(VERIFIED_USE_EVENTS) & grant_match
    changed = event.in_(PERMISSION_CHANGE_EVENTS)
    windows_priv = event == 'windows_privileged_logon'
    linux_sudo = event == 'linux_sudo'
    github_repo = event == 'github_repo_activity' 
    grouped = db.query(
        Activity.account_id.label('account_id'),
        func.sum(case((success, 1), else_=0)).label('logins'),
        func.sum(case((failed, 1), else_=0)).label('failures'),
        func.sum(case((resource_used, 1), else_=0)).label('uses'),
        func.count(func.distinct(case((or_(success, resource_used), func.date(Activity.occurred_at)), else_=None))).label('active_days'),
        func.count(func.distinct(case((resource_used, Activity.resource), else_=None))).label('used_resources'),
        func.sum(case((changed, 1), else_=0)).label('changes'),
        func.sum(case((windows_priv, 1), else_=0)).label('windows_privileged'),
        func.sum(case((linux_sudo, 1), else_=0)).label('linux_sudo'),
        func.sum(case((github_repo, 1), else_=0)).label('github_repo'),
        func.sum(case((resource_used & (Activity.occurred_at < cut1), 1), else_=0)).label('month1_use'),
        func.sum(case((resource_used & (Activity.occurred_at >= cut1) & (Activity.occurred_at < cut2), 1), else_=0)).label('month2_use'),
        func.sum(case((resource_used & (Activity.occurred_at >= cut2), 1), else_=0)).label('month3_use'),
        func.max(case((resource_used, Activity.occurred_at), else_=None)).label('last_resource_use'),
    ).filter(Activity.occurred_at >= since, Activity.occurred_at <= as_of).group_by(Activity.account_id).all()
    activity_by_account = {r.account_id: r for r in grouped}
    managed_findings = summarize_governed_resources(db, since=since, as_of=as_of)
    result = []
    for a in accounts:
        grants = [e for e in a.entitlements if e.active]
        if (a.status or "active").lower() != "active":
            continue
        emp = a.employee
        aggregate = activity_by_account.get(a.id)
        login_count = int(aggregate.logins or 0) if aggregate else 0
        failed_count = int(aggregate.failures or 0) if aggregate else 0
        used_count = int(aggregate.uses or 0) if aggregate else 0
        active_days = int(aggregate.active_days or 0) if aggregate else 0
        resources_used = int(aggregate.used_resources or 0) if aggregate else 0
        changes_count = int(aggregate.changes or 0) if aggregate else 0
        month1 = int(aggregate.month1_use or 0) if aggregate else 0
        month2 = int(aggregate.month2_use or 0) if aggregate else 0
        month3 = int(aggregate.month3_use or 0) if aggregate else 0
        last_event_use = aggregate.last_resource_use if aggregate else None
        verified_dates = ([last_event_use] if last_event_use is not None else [])
        # A connector's last_used_at must be supported by actual entitlement-use
        # evidence; authentication or log collection presence is not proof of use.
        verified_dates.extend(e.last_used_at for e in grants if e.last_used_at is not None
                              and e.evidence_source and e.last_used_at <= as_of)
        age = min(window_days + 1, max(0, (as_of - max(verified_dates)).days)) if verified_dates else 0
        priv_count = sum((e.permission or "").lower() in PRIVILEGED for e in grants)
        sensitive_count = sum((e.sensitivity or "").lower() in {"high", "critical"} for e in grants)
        # Never apply the V1 demo department keyword heuristic to real organizations.
        # A governed access mapping supplies out-of-scope group findings instead.
        mismatch_count = 0
        # No reliable service-account data in v1 DB. It must be supplied by an identity connector.
        snapshot = snapshots.get(emp.id) if emp else None
        group_metrics = group_summary.get(emp.id, {}) if emp else {}
        group_count = group_metrics.get('total', 0)
        privileged_group_count = group_metrics.get('privileged', 0)
        unmapped_group_count = group_metrics.get('unknown', 0)
        mapped_access_group_count = group_metrics.get('access', 0)
        non_access_group_count = group_metrics.get('non_access', 0)
        out_of_scope_group_count = group_metrics.get('out_of_scope', 0)
        group_catalog_coverage_fraction = ((group_count - unmapped_group_count) / group_count
                                            if group_count else 0.0)
        pending_transfers = [(t_id, when) for t_id, when in transfer_by_employee.get(emp.id, [])
                             if (t_id, a.id) not in already_reviewed] if emp else []
        transfer_n, manager_changes, department_changes, org_unit_changes, last_transfer = (
            transfers_by_emp.get(emp.id, (0, 0, 0, 0, None)) if emp else (0, 0, 0, 0, None))
        group_changes_n = groups_changed_by_emp.get(emp.id, 0) if emp else 0
        # A snapshot with groups_complete=true is evidence that zero groups
        # means a known empty set; otherwise missing must remain unknown.
        group_data_known = bool(snapshot and snapshot.groups_complete)
        transfer_history_known = bool(snapshot and snapshot.transfer_history_complete)
        reporting_known = bool(snapshot and snapshot.reporting_manager)
        dept_mismatch = int(bool(snapshot and snapshot.ad_department and emp and
                                 snapshot.ad_department.casefold() != (emp.department or '').casefold()))
        transfer_age = max(0, (as_of - last_transfer).days) if last_transfer else 0
        coverage = coverage_by_platform.get(a.platform)
        coverage_known = isinstance(coverage, (int, float)) and 0 <= coverage <= window_days
        result.append({
            "account_id": a.id, "employee_code": emp.code if emp else None,
            "managed_policy_conflict_count": managed_findings.get(a.id,{}).get('managed_policy_conflict_count',0),
            "managed_policy_conflict_resources": managed_findings.get(a.id,{}).get('managed_policy_conflict_resources',[]),
            "username": a.username, "employee_status": emp.status.lower() if emp else "unmapped",
            "account_status": a.status.lower(), "platform": a.platform,
            "department": emp.department if emp else "Unknown", "account_type": getattr(a, "account_type", "unknown") or "unknown",
            "permission_profile": "privileged" if priv_count else "standard",
            "entitlement_count": len(grants), "privileged_entitlements": priv_count,
            "sensitive_entitlements": sensitive_count, "outside_role_count": mismatch_count,
            "successful_logins_window": login_count, "failed_logins_window": failed_count,
            "resource_use_events_window": used_count,
            "active_days_window": active_days,
            "distinct_resources_used_window": resources_used,
            "permission_changes_window": changes_count,
            "resource_uses_month_1": month1,
            "resource_uses_month_2": month2,
            "resource_uses_month_3": month3,
            "use_age_days": age, "use_evidence_observed": int(bool(verified_dates)),
            "log_coverage_days": round(float(coverage), 3) if coverage_known else 0,
            "log_coverage_known": int(coverage_known),
            "ad_group_count": group_count, "privileged_ad_group_count": privileged_group_count,
            "mapped_access_ad_group_count": mapped_access_group_count,
            "non_access_ad_group_count": non_access_group_count,
            "unmapped_ad_group_count": unmapped_group_count,
            "out_of_scope_ad_group_count": out_of_scope_group_count,
            "group_catalog_coverage_fraction": round(group_catalog_coverage_fraction, 4),
            "pending_transfer_count": len(pending_transfers),
            # IDs are evidence, not ML features, and are frozen for human review.
            "pending_transfer_ids": [event_id for event_id, _ in pending_transfers],
            "windows_privileged_logon_events": int(aggregate.windows_privileged or 0) if aggregate else 0,
            "linux_sudo_events": int(aggregate.linux_sudo or 0) if aggregate else 0,
            "github_repo_activity_events": int(aggregate.github_repo or 0) if aggregate else 0,
            # Observing a signal does NOT certify the collection is complete.
            "windows_privileged_logon_coverage_known": int(signal_coverage_days.get((a.platform, 'windows_privileged_logon'), 0) >= .995 * window_days),
            "linux_sudo_coverage_known": int(signal_coverage_days.get((a.platform, 'linux_sudo'), 0) >= .995 * window_days),
            "github_repo_activity_coverage_known": int(signal_coverage_days.get((a.platform, 'github_repo_activity'), 0) >= .995 * window_days),
            "ad_group_data_known": int(group_data_known),
            "group_changes_window": group_changes_n, "transfers_window": transfer_n,
            "manager_changes_window": manager_changes,
            "department_changes_window": department_changes,
            "org_unit_changes_window": org_unit_changes,
            "recent_transfer_flag": int(transfer_n > 0),
            "days_since_last_transfer": transfer_age, "transfer_history_known": int(transfer_history_known),
            "ad_department_mismatch": dept_mismatch, "ad_reporting_known": int(reporting_known),
            "ad_reporting_manager": snapshot.reporting_manager if snapshot else None,
            "ad_org_unit": snapshot.org_unit if snapshot else None,
        })
    return result
