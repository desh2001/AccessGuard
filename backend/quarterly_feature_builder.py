"""Quarterly Feature Builder — aggregates 90-day account features for Aegis V9 ML.

Source of truth for feature schemas:
- `ml/backend/app/ml/platforms/common.py`
- `ml/backend/app/ml/platforms/windows.py`
- `ml/backend/app/ml/platforms/linux.py`
- `ml/backend/app/ml/platforms/github.py`

Guarantees:
1. Exactly one feature row per active technical account for the review cycle.
2. Aggregated over the exact 90-day UTC window.
3. No usernames, emails, employee names, passwords, tokens or labels inside `features`.
4. Generic LOGIN events do NOT increment `resource_use_events_window`.
5. Missing coverage is flagged explicitly (`log_coverage_known=0`); never fabricated as normal 0.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from collections import defaultdict

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from models import (
    Identity, System, Account, AccessGrant, ActivityEvent,
    ActivityCoverage, ADGroupCatalog, ADGroupMembershipHistory,
    EmployeeTransfer, ManagedResourcePolicy, now_utc
)

# Canonical platform aliases (matching Aegis V8/V9 platform router)
PLATFORM_ALIASES = {
    'win': 'windows',
    'windows': 'windows',
    'windows ad': 'windows',
    'active directory': 'windows',
    'lin': 'linux',
    'linux': 'linux',
    'ubuntu': 'linux',
    'rhel': 'linux',
    'debian': 'linux',
    'centos': 'linux',
    'gh': 'github',
    'gth': 'github',
    'github': 'github',
    'github enterprise': 'github',
}

SUPPORTED_PLATFORMS = ('windows', 'linux', 'github')


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_platform(system: System) -> str | None:
    """Return canonical platform key ('windows', 'linux', 'github') or None if unsupported."""
    if system.platform:
        cand = PLATFORM_ALIASES.get(system.platform.strip().lower())
        if cand:
            return cand
    if system.id:
        cand = PLATFORM_ALIASES.get(system.id.strip().lower())
        if cand:
            return cand
    if system.name:
        cand = PLATFORM_ALIASES.get(system.name.strip().lower())
        if cand:
            return cand
        # Substring heuristics
        name_lower = system.name.lower()
        if 'windows' in name_lower or 'active directory' in name_lower:
            return 'windows'
        if 'linux' in name_lower:
            return 'linux'
        if 'github' in name_lower:
            return 'github'
    return None


def calculate_coverage_days(
    db: Session,
    platform: str,
    account_id: int | None,
    window_start: datetime,
    window_end: datetime,
) -> tuple[float, int]:
    """Calculate verified coverage days from non-overlapping complete attestations.

    Returns (coverage_days, coverage_known_flag).
    """
    query = select(ActivityCoverage).where(
        ActivityCoverage.platform == platform,
        ActivityCoverage.is_complete == 1,
        ActivityCoverage.start_at < window_end,
        ActivityCoverage.end_at > window_start,
    )
    if account_id is not None:
        query = query.where(
            (ActivityCoverage.account_id == account_id) | (ActivityCoverage.account_id.is_(None))
        )
    else:
        query = query.where(ActivityCoverage.account_id.is_(None))

    attestations = db.scalars(query).all()
    if not attestations:
        return 0.0, 0

    # Merge overlapping intervals inside the 90-day window
    intervals: list[tuple[datetime, datetime]] = []
    for att in attestations:
        start = max(_ensure_utc(att.start_at), _ensure_utc(window_start))
        end = min(_ensure_utc(att.end_at), _ensure_utc(window_end))
        if start < end:
            intervals.append((start, end))

    if not intervals:
        return 0.0, 0

    intervals.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [intervals[0]]
    for cur_start, cur_end in intervals[1:]:
        last_start, last_end = merged[-1]
        if cur_start <= last_end:
            merged[-1] = (last_start, max(last_end, cur_end))
        else:
            merged.append((cur_start, cur_end))

    total_seconds = sum((end - start).total_seconds() for start, end in merged)
    coverage_days = round(total_seconds / 86400.0, 2)
    return min(90.0, coverage_days), 1


def build_account_features(
    db: Session,
    window_start: datetime,
    window_end: datetime,
    account_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Build exactly one 90-day feature row per active account.

    Returns records ready for `POST /v1/score/accounts`:
    [
        {
            "account_id": str(account.id),
            "platform": "windows" | "linux" | "github",
            "features": { ... }
        },
        ...
    ]
    """
    window_duration_days = (window_end - window_start).days or 90
    month_1_end = window_start + timedelta(days=30)
    month_2_end = window_start + timedelta(days=60)

    # 1. Fetch in-scope accounts
    acc_query = select(Account).where(Account.status == 'Active')
    if account_ids:
        acc_query = acc_query.where(Account.id.in_(account_ids))
    accounts = db.scalars(acc_query).all()

    # Pre-fetch managed resource policies
    managed_policies = {
        p.resource_key.lower(): p for p in db.scalars(select(ManagedResourcePolicy)).all()
    }

    records: list[dict[str, Any]] = []

    for acc in accounts:
        system = acc.system or db.get(System, acc.system_id)
        platform_key = resolve_platform(system) if system else None
        platform_display = (
            'Windows AD' if platform_key == 'windows'
            else ('Linux' if platform_key == 'linux'
            else ('GitHub' if platform_key == 'github'
            else (system.name if system else 'Unknown')))
        )

        identity = acc.identity or (db.get(Identity, acc.identity_id) if acc.identity_id else None)
        department = identity.department.lower().strip() if identity else 'unmapped'
        
        # V11: Read explicit Account.account_type directly. No username/identity heuristics.
        raw_act = (getattr(acc, 'account_type', None) or 'unknown').strip().lower()
        valid_types = {'human', 'service', 'shared', 'emergency', 'vendor', 'workload', 'machine', 'unknown'}
        account_type = raw_act if raw_act in valid_types else 'unknown'

        # Entitlements & grants
        grants = acc.grants or db.scalars(
            select(AccessGrant).where(AccessGrant.account_id == acc.id, AccessGrant.status == 'Active')
        ).all()
        entitlement_count = len(grants)
        privileged_entitlements = sum(1 for g in grants if g.privilege == 1)
        sensitive_entitlements = sum(1 for g in grants if (g.sensitivity or '').lower() in ('high', 'critical', 'sensitive'))

        permission_profile = (
            'privileged' if privileged_entitlements > 0
            else ('standard' if entitlement_count > 0 else 'none')
        )

        # 2. Activity events within 90-day window
        events = db.scalars(
            select(ActivityEvent).where(
                ActivityEvent.account_id == acc.id,
                ActivityEvent.occurred_at >= window_start,
                ActivityEvent.occurred_at <= window_end,
            ).order_by(ActivityEvent.occurred_at.asc())
        ).all()

        successful_logins = 0
        failed_logins = 0
        resource_uses = 0
        resource_uses_m1 = 0
        resource_uses_m2 = 0
        resource_uses_m3 = 0
        distinct_resources: set[str] = set()
        active_calendar_days: set[str] = set()
        permission_changes = 0

        # Special contextual signals
        win_priv_logons = 0
        linux_sudo = 0
        github_repo_events = 0

        most_recent_use: datetime | None = None

        for ev in events:
            action_lower = (ev.action or '').lower()
            event_type_lower = (ev.event_type or '').lower()
            outcome_lower = (ev.outcome or '').lower()
            is_success = outcome_lower == 'success'

            day_str = ev.occurred_at.strftime('%Y-%m-%d')
            active_calendar_days.add(day_str)

            # Check if login
            is_login = any(k in action_lower or k in event_type_lower for k in ('login', 'logon', 'auth', 'interactive', 'session'))
            if is_login:
                if is_success:
                    successful_logins += 1
                else:
                    failed_logins += 1

            # Check permission change
            if any(k in action_lower for k in ('grant', 'revoke', 'permission_change', 'role_change', 'group_add')):
                permission_changes += 1

            # Check special contextual signals
            if '4672' in action_lower or 'privileged logon' in action_lower:
                win_priv_logons += 1
            if 'sudo' in action_lower or 'sudo' in event_type_lower:
                linux_sudo += 1
            if any(k in action_lower for k in ('repo', 'git_push', 'pull_request', 'commit', 'branch')):
                github_repo_events += 1

            # Resource use: must NOT be generic login
            # Attributable action on a resource/file/repo/database/API
            is_resource_use = (
                not is_login
                and (
                    ev.resource_key is not None
                    or any(k in action_lower for k in ('query', 'read', 'write', 'execute', 'api', 'repo', 'file', 'checkout', 'export', 'update', 'delete', 'select', 'sudo'))
                    or (ev.resource_key and ev.resource_key.lower() in managed_policies)
                )
            )

            if is_resource_use and is_success:
                resource_uses += 1
                if ev.resource_key:
                    distinct_resources.add(ev.resource_key)
                elif ev.action:
                    distinct_resources.add(ev.action)

                most_recent_use = ev.occurred_at

                ev_time = _ensure_utc(ev.occurred_at)
                if ev_time < month_1_end:
                    resource_uses_m1 += 1
                elif ev_time < month_2_end:
                    resource_uses_m2 += 1
                else:
                    resource_uses_m3 += 1

        # Use evidence observed and age
        # Fall back to AccessGrant.last_verified_use if no events in window but historically recorded
        if most_recent_use is None:
            latest_grant_use = max(
                (_ensure_utc(g.last_verified_use) for g in grants if g.last_verified_use),
                default=None
            )
            if latest_grant_use and latest_grant_use >= window_start:
                most_recent_use = latest_grant_use

        if most_recent_use is not None:
            use_evidence_observed = 1
            use_age_days = max(0, (window_end - _ensure_utc(most_recent_use)).days)
        else:
            use_evidence_observed = 0
            use_age_days = 0

        # Telemetry coverage
        cov_days, cov_known = calculate_coverage_days(
            db, platform_key or 'unknown', acc.id, window_start, window_end
        )

        # 3. HR Transfers & Reporting scope
        transfers_count = 0
        recent_transfer = 0
        dept_changes = 0
        mgr_changes = 0
        if identity:
            transfers = db.scalars(
                select(EmployeeTransfer).where(
                    EmployeeTransfer.identity_id == identity.id,
                    EmployeeTransfer.effective_at >= window_start,
                    EmployeeTransfer.effective_at <= window_end,
                )
            ).all()
            transfers_count = len(transfers)
            recent_threshold = window_end - timedelta(days=30)
            recent_transfer = 1 if any(_ensure_utc(t.effective_at) >= recent_threshold for t in transfers) else 0
            dept_changes = sum(1 for t in transfers if t.from_department != t.to_department)
            mgr_changes = sum(1 for t in transfers if t.from_manager != t.to_manager)

        # 4. AD Groups & Governance
        ad_group_count = 0
        privileged_ad_groups = 0
        ad_group_data_known = 0
        mapped_access_groups = 0
        unmapped_ad_groups = 0
        group_catalog_coverage_fraction = 1.0
        out_of_scope_groups = 0
        group_changes = 0

        if identity and platform_key == 'windows':
            memberships = db.scalars(
                select(ADGroupMembershipHistory).where(
                    ADGroupMembershipHistory.identity_id == identity.id,
                    ADGroupMembershipHistory.is_active == 1,
                )
            ).all()
            if memberships:
                ad_group_data_known = 1
                ad_group_count = len(memberships)
                group_keys = [m.group_key for m in memberships]
                catalogs = {
                    c.group_key: c
                    for c in db.scalars(
                        select(ADGroupCatalog).where(ADGroupCatalog.group_key.in_(group_keys))
                    ).all()
                }
                for gk in group_keys:
                    cat = catalogs.get(gk)
                    if cat:
                        if cat.access_relevance == 'access':
                            mapped_access_groups += 1
                        if (cat.privilege_tier or '').lower() in ('tier_0', 'tier_1', 'admin', 'privileged'):
                            privileged_ad_groups += 1
                        if cat.allowed_departments and identity.department.lower() not in cat.allowed_departments.lower():
                            out_of_scope_groups += 1
                    else:
                        unmapped_ad_groups += 1

                if ad_group_count > 0:
                    group_catalog_coverage_fraction = round(
                        (ad_group_count - unmapped_ad_groups) / float(ad_group_count), 4
                    )
        elif platform_key in ('linux', 'github'):
            ad_group_data_known = 1

        # 5. Assemble exact platform feature dictionary
        common_features = {
            'department': department,
            'account_type': account_type,
            'permission_profile': permission_profile,
            'platform': platform_display,
            'entitlement_count': entitlement_count,
            'privileged_entitlements': privileged_entitlements,
            'sensitive_entitlements': sensitive_entitlements,
            'successful_logins_window': successful_logins,
            'failed_logins_window': failed_logins,
            'resource_use_events_window': resource_uses,
            'active_days_window': len(active_calendar_days),
            'distinct_resources_used_window': len(distinct_resources),
            'permission_changes_window': permission_changes,
            'use_age_days': use_age_days,
            'use_evidence_observed': use_evidence_observed,
            'resource_uses_month_1': resource_uses_m1,
            'resource_uses_month_2': resource_uses_m2,
            'resource_uses_month_3': resource_uses_m3,
            'log_coverage_days': cov_days,
            'log_coverage_known': cov_known,
            'group_changes_window': group_changes,
            'transfers_window': transfers_count,
            'recent_transfer_flag': recent_transfer,
            'out_of_scope_ad_group_count': out_of_scope_groups,
        }

        if platform_key == 'windows':
            features = {
                **common_features,
                'ad_group_count': ad_group_count,
                'privileged_ad_group_count': privileged_ad_groups,
                'ad_group_data_known': ad_group_data_known,
                'mapped_access_ad_group_count': mapped_access_groups,
                'unmapped_ad_group_count': unmapped_ad_groups,
                'group_catalog_coverage_fraction': group_catalog_coverage_fraction,
                'manager_changes_window': mgr_changes,
                'department_changes_window': dept_changes,
                'ad_department_mismatch': 1 if dept_changes > 0 else 0,
                'windows_privileged_logon_events': win_priv_logons,
                'windows_privileged_logon_coverage_known': cov_known,
            }
        elif platform_key == 'linux':
            features = {
                **common_features,
                'ad_group_data_known': ad_group_data_known,
                'privileged_ad_group_count': privileged_ad_groups,
                'linux_sudo_events': linux_sudo,
                'linux_sudo_coverage_known': cov_known,
            }
        elif platform_key == 'github':
            features = {
                **common_features,
                'github_repo_activity_events': github_repo_events,
                'github_repo_activity_coverage_known': cov_known,
                'ad_group_data_known': ad_group_data_known,
                'unmapped_ad_group_count': unmapped_ad_groups,
            }
        else:
            # Unsupported platform (e.g. GitLab, Salesforce, Slack)
            features = {
                **common_features,
                'unsupported': True,
            }

        records.append({
            'account_id': str(acc.id),
            'platform': platform_display,
            'features': features,
            '_internal': {
                'account_id_int': acc.id,
                'canonical_platform': platform_key,
                'identity_id': acc.identity_id,
                'identity_status': identity.status if identity else 'unmapped',
                'username': acc.username,
                'entitlement_count': entitlement_count,
                'transfers_count': transfers_count,
                'recent_transfer': recent_transfer,
                'coverage_days': cov_days,
                'coverage_known': cov_known,
            }
        })

    return records
