"""Periodic access-certification triage, never a real-time EDR alert engine.

Industry expert's requirement: every configurable review period, build a small queue
of accounts with meaningful entitlement/lifecycle concerns, not a mandatory quota
of random normal accounts. All decisions remain with an authorized human.

Review budget is a *maximum target*, not a quota. If there are only 5 deserving
cases, a 10% budget does not require filling the other 995 slots with random users.
Unknown evidence and deferred candidates are tracked explicitly rather than
being falsely certified as safe.
"""
from __future__ import annotations
import math
from sqlalchemy.orm import Session
from .periodic_features import aggregate_accounts
from .periodic_model import predict_periodic  # explicit legacy-model tests only
from .platform_models import (platform_key, predict_platform, load_all_platforms,
                              MODEL_SCHEMA_VERSION, SUPPORTED_MODELS)

DEFAULT_POLICY_REVIEW_THRESHOLD = 25
DEFAULT_ML_REVIEW_PERCENTILE = .95
# Require almost-complete (99.5%) coverage to reason from an *absence* of use.
# 90% coverage could miss nine whole days. Even 99.5% is a configurable,
# organization-specific assumption and must be backed by source attestation.
MIN_COVERAGE_FRACTION = .995


def make_review_queue(rows, review_budget_percent=10.0, artifact=None,
                      policy_threshold=DEFAULT_POLICY_REVIEW_THRESHOLD,
                      anomaly_threshold=DEFAULT_ML_REVIEW_PERCENTILE, platform_models=None):
    if not (0 < review_budget_percent <= 100):
        raise ValueError('review_budget_percent must be in (0,100]')
    if not (0 <= policy_threshold <= 100):
        raise ValueError('policy_threshold must be 0..100')
    if not (0 < anomaly_threshold <= 1):
        raise ValueError('anomaly_threshold must be in (0,1]')
    identifiers = [r['account_id'] for r in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Each account_id must occur once per review cycle')

    anomaly_values = [None] * len(rows)
    model_keys = [platform_key(row.get('platform')) for row in rows]
    model_versions = [None] * len(rows)
    if platform_models is not None:
        # No cross-platform fallbacks. GitLab and unknowns remain unscored.
        for platform in SUPPORTED_MODELS:
            trained = platform_models.get(platform)
            if trained is None:
                continue
            if trained.get('model_key') != platform or trained.get('schema') != MODEL_SCHEMA_VERSION:
                raise ValueError(f'Invalid/mismatched {platform} artifact')
            eligible = [i for i, row in enumerate(rows) if model_keys[i] == platform and
                        bool(row.get('log_coverage_known')) and
                        float(row.get('log_coverage_days') or 0) >=
                        MIN_COVERAGE_FRACTION * float(row.get('period_days', 90))]
            if eligible:
                predictions = predict_platform([rows[i] for i in eligible], trained)
                for index, value in zip(eligible, predictions):
                    anomaly_values[index] = value
                    model_versions[index] = MODEL_SCHEMA_VERSION
    elif artifact:
        # Backward-compatible direct use for legacy tests, NOT the V8 API path.
        eligible = [i for i, row in enumerate(rows)
                    if bool(row.get('log_coverage_known')) and
                    float(row.get('log_coverage_days') or 0) >=
                    MIN_COVERAGE_FRACTION * float(row.get('period_days', 90))]
        if eligible:
            predictions = predict_periodic([rows[i] for i in eligible], artifact)
            for index, value in zip(eligible, predictions):
                anomaly_values[index] = value

    records = []
    for row, anomaly, model_key, model_version in zip(rows, anomaly_values, model_keys, model_versions):
        reasons = []
        score = 0
        status = str(row.get('employee_status') or 'unmapped').strip().lower()
        pending_transfer_count = int(row.get('pending_transfer_count', row.get('transfers_window', 0)) or 0)
        # Internal transfers must ALWAYS be presented until a human reviews
        # EVERY currently active linked application account; no threshold bypass.
        mandatory = status != 'active' or pending_transfer_count > 0
        window_days = float(row.get('period_days', 90))
        coverage_days = float(row.get('log_coverage_days') or 0)
        coverage_known = bool(row.get('log_coverage_known'))
        sufficient_coverage = coverage_known and coverage_days >= MIN_COVERAGE_FRACTION * window_days

        if mandatory:
            score += 60
            reasons.append('Mandatory HR/identity verification: inactive employee or unmapped account')
        if row.get('outside_role_count', 0) > 0:
            score += 35
            reasons.append('Access outside demonstration role policy; verify business justification')
        if row.get('privileged_entitlements', 0) > 0:
            score += 15
            reasons.append('Privileged entitlements require additional scrutiny')
        if row.get('sensitive_entitlements', 0) > 0:
            score += 10
            reasons.append('High-sensitivity entitlements')
        if pending_transfer_count > 0:
            score += 40
            reasons.append('MANDATORY: employee transferred or reporting scope changed; re-certify this application account')
        elif row.get('transfers_window', 0) > 0:
            reasons.append('Prior in-window transfer is already individually reviewed for this account')
        if row.get('group_changes_window', 0) > 0:
            score += 15
            reasons.append('Active Directory group membership changed during review period')
        if row.get('privileged_ad_group_count', 0) > 0:
            score += 10
            reasons.append('Privileged AD group membership backed by an approved organization-specific catalog')
        if row.get('out_of_scope_ad_group_count', 0) > 0:
            score += 35
            reasons.append('Access-bearing AD group incompatible with current department per approved catalog')
        if row.get('unmapped_ad_group_count', 0) > 0:
            reasons.append('Unclassified AD groups require governance mapping; no privilege inference from group names')
        if row.get('ad_department_mismatch', 0) > 0:
            score += 15
            reasons.append('HR vs AD department differs; verify synchronization or transfer')
        # Only organization-approved BUSINESS asset policy mismatches. Personal
        # browsing/media or unknown applications are never review triggers.
        if row.get('managed_policy_conflict_count', 0) > 0:
            score += 35
            reasons.append('Managed business resource use differs from approved access policy; verify authorized business need')
        if row.get('permission_changes_window', 0) > 2:
            score += 15
            reasons.append('Multiple entitlement changes in the review period')

        # An authentication event alone is not evidence that a specific grant
        # is needed. Absence of use matters only after sufficient source coverage.
        last_use_known = bool(row.get('use_evidence_observed', 0))
        if sufficient_coverage:
            if not last_use_known:
                score += 25
                reasons.append('No verified resource use during the covered period')
            elif float(row.get('use_age_days') or 0) >= window_days:
                score += 25
                reasons.append('Last verified resource use predates this review period')
        elif not coverage_known:
            reasons.append('Missing usage-collection coverage: evidence must be obtained')
        else:
            reasons.append('Partial usage-collection coverage: no inactivity conclusion possible')

        if anomaly is not None and anomaly >= anomaly_threshold:
            reasons.append('Access/account behavior is unusual relative to normal reference peers (ML advisory)')

        score = min(100, score)
        group_mapping_gap = bool(row.get('unmapped_ad_group_count', 0)) or (
            bool(row.get('ad_group_count', 0)) and not bool(row.get('ad_group_data_known', 0)))
        evidence_gap = (not sufficient_coverage) or group_mapping_gap
        # Score signals are separate: ML rarity is NOT the probability that
        # continued access is unnecessary, and does not auto-revoke access.
        candidate = mandatory or score >= policy_threshold or (anomaly is not None and anomaly >= anomaly_threshold)
        # Policy severity is the primary ordering signal. The ML novelty score
        # only breaks ties between equally severe policy cases and can add
        # otherwise overlooked candidates when capacity permits. Giving a
        # rare-but-benign anomaly a large bonus can displace a known concern.
        ranking = score + (anomaly or 0) * 0.001
        records.append({
            'account_id': row['account_id'], 'username': row['username'],
            'employee_code': row.get('employee_code'), 'platform': row['platform'],
            'pending_transfer_ids': list(row.get('pending_transfer_ids') or []),
            'pending_transfer_count': pending_transfer_count,
            'evidence_gap': evidence_gap,
            'department': row.get('department', 'Unknown'), 'employee_status': status,
            'reporting_manager_ref': row.get('ad_reporting_manager'), 'ad_org_unit': row.get('ad_org_unit'),
            'entitlement_count': row.get('entitlement_count', 0), 'mandatory': mandatory,
            'policy_score': score, 'anomaly_percentile': anomaly,
            'ml_model_key': model_key if model_version else None,
            'ml_model_version': model_version,
            'ml_model_eligible_platform': model_key is not None,
            'ranking_score': round(ranking, 3), 'candidate': candidate,
            'evidence_sufficient_for_inactivity': sufficient_coverage,
            'reasons': reasons or ['No configured review triggers; account is still subject to organization policy'],
            'activity_summary': {
                'successful_logins': row.get('successful_logins_window', 0),
                'resource_use_events': row.get('resource_use_events_window', 0),
                'source_signal': ({
                    'windows': {'event': 'windows_privileged_logon',
                                'events': row.get('windows_privileged_logon_events', 0),
                                'coverage_known': bool(row.get('windows_privileged_logon_coverage_known', 0))},
                    'linux': {'event': 'linux_sudo',
                              'events': row.get('linux_sudo_events', 0),
                              'coverage_known': bool(row.get('linux_sudo_coverage_known', 0))},
                    'github': {'event': 'github_repo_activity',
                               'events': row.get('github_repo_activity_events', 0),
                               'coverage_known': bool(row.get('github_repo_activity_coverage_known', 0))},
                }).get(model_key),
                'distinct_active_days': row.get('active_days_window', 0),
                'verified_use_observed': last_use_known,
                'log_coverage_known': coverage_known,
                'log_coverage_days': coverage_days,
                'window_days': window_days,
                'ad_group_count': row.get('ad_group_count', 0),
                'mapped_access_ad_group_count': row.get('mapped_access_ad_group_count', 0),
                'non_access_ad_group_count': row.get('non_access_ad_group_count', 0),
                'unmapped_ad_group_count': row.get('unmapped_ad_group_count', 0),
                'out_of_scope_ad_group_count': row.get('out_of_scope_ad_group_count', 0),
                'group_catalog_coverage_fraction': row.get('group_catalog_coverage_fraction', 0.0),
                'pending_transfer_count': pending_transfer_count,
                'ad_group_data_known': bool(row.get('ad_group_data_known', 0)),
                'privileged_ad_group_count': row.get('privileged_ad_group_count', 0),
                'ad_group_changes': row.get('group_changes_window', 0),
                'employee_transfers': row.get('transfers_window', 0),
                'manager_changes': row.get('manager_changes_window', 0),
                'department_changes': row.get('department_changes_window', 0),
                'org_unit_changes':row.get('org_unit_changes_window', 0),
                'transfer_history_known': bool(row.get('transfer_history_known', 0)),
                'managed_policy_conflict_count': row.get('managed_policy_conflict_count', 0),
                'managed_policy_conflict_resources': row.get('managed_policy_conflict_resources', []),
                'monthly_verified_use': [row.get('resource_uses_month_1', 0),
                                         row.get('resource_uses_month_2', 0),
                                         row.get('resource_uses_month_3', 0)],
            },
        })

    total = len(records)
    capacity = math.ceil(total * review_budget_percent / 100) if total else 0
    urgent = sorted((r for r in records if r['mandatory']),
                    key=lambda r: (-r['ranking_score'], str(r['account_id'])))
    candidates = sorted((r for r in records if r['candidate'] and not r['mandatory']),
                        key=lambda r: (-r['ranking_score'], str(r['account_id'])))
    slots = max(0, capacity - len(urgent))
    selected = urgent + candidates[:slots]
    selected_ids = {r['account_id'] for r in selected}
    for row in records:
        if row['mandatory']:
            priority = 'mandatory'
        elif row['account_id'] in selected_ids:
            priority = 'selected'
        elif row['candidate']:
            priority = 'deferred_candidate'
        elif row['evidence_gap']:
            priority = 'insufficient_evidence'
        else:
            priority = 'deprioritized_not_certified'
        row['review_priority'] = priority
        row['automatically_certified'] = False
        row.pop('candidate')

    ordering = {'mandatory': 0, 'selected': 1, 'deferred_candidate': 2,
                'insufficient_evidence': 3, 'deprioritized_not_certified': 4}
    records.sort(key=lambda r: (ordering[r['review_priority']], -r['ranking_score'], str(r['account_id'])))
    counts = {value: sum(r['review_priority'] == value for r in records) for value in ordering}
    return {
        'total_accounts': total, 'target_review_capacity': capacity,
        'selected_count': len(selected), 'mandatory_count': len(urgent),
        'candidate_count': len(urgent) + len(candidates),
        'deferred_candidate_count': counts['deferred_candidate'],
        'insufficient_evidence_count': counts['insufficient_evidence'],
        'deprioritized_count': counts['deprioritized_not_certified'],
        'illustrative_workload_reduction_percent': round(100 * (total - len(selected)) / total, 2) if total else 0,
        'budget_exceeded_by_mandatory_cases': len(urgent) > capacity,
        'ml_model_loaded': bool(platform_models) if platform_models is not None else artifact is not None,
        'ml_model_used': any(v is not None for v in anomaly_values),
        'platform_model_loaded': {p: p in (platform_models or {}) for p in SUPPORTED_MODELS}
                                 if platform_models is not None else {},
        'platform_model_scored': {p: sum(k == p and v is not None for k,v in zip(model_keys, anomaly_values))
                                  for p in SUPPORTED_MODELS},
        'unsupported_platform_accounts': sum(k is None for k in model_keys),
        'model_provenance': ('Three independent platform models; synthetic-only until externally reviewed')
                            if platform_models is not None else
                            (artifact.get('metadata',{}).get('disclaimer') if artifact else None),
        'model_schema_version': MODEL_SCHEMA_VERSION if platform_models is not None else
                                (artifact.get('schema') if artifact else None),
        'mandatory_transfer_accounts': sum(r['pending_transfer_count'] > 0 for r in records),
        'unmapped_ad_group_accounts': sum('Unclassified AD groups' in ' '.join(r['reasons']) for r in records),
        'policy_review_threshold': policy_threshold,
        'ml_outlier_percentile_threshold': anomaly_threshold,
        'queue_policy': 'Budget is a cap for nonmandatory candidates, NOT a quota. All pending transfers and lifecycle cases override budget.',
        'unresolved_issues': 'Deferred candidates and insufficient-evidence accounts need a policy-approved follow-up. None are certified.',
        'non_selection_means': 'Not selected for this queue; NOT certified as safe or approved to retain',
        'accounts': records,
    }


def periodic_preview(db: Session, window_days=90, review_budget_percent=10.0, as_of=None,
                     max_results=None, policy_threshold=DEFAULT_POLICY_REVIEW_THRESHOLD,
                     anomaly_threshold=DEFAULT_ML_REVIEW_PERCENTILE):
    rows = aggregate_accounts(db, as_of=as_of, window_days=window_days)
    for row in rows:
        row['period_days'] = window_days
    # Never score 30/60/180-day windows with a model calibrated for 90-day records.
    platform_models = load_all_platforms() if window_days == 90 else {}
    result = make_review_queue(rows, review_budget_percent, platform_models=platform_models,
                               policy_threshold=policy_threshold, anomaly_threshold=anomaly_threshold)
    result['model_window_note'] = ('Three separate 90-day platform models; missing model = rule-only for that source'
                                   if window_days == 90 else 'Rule-only: platform models trained for 90-day windows')
    result['review_window_days'] = window_days
    result['as_of'] = str(as_of) if as_of else 'current UTC'
    result['ml_scored_accounts'] = sum(a['anomaly_percentile'] is not None for a in result['accounts'])
    result['evidence_gaps'] = sum(a['evidence_gap'] for a in result['accounts'])
    result['limited_coverage_accounts'] = sum(0 < r['log_coverage_days'] < MIN_COVERAGE_FRACTION * window_days for r in rows)
    result['review_effort_note'] = ('Preview counts accounts, not hours saved. Timed audits and independently reviewed labels are needed. '
                                    'Unselected is not the same as certified safe.')
    result['data_quality_warning'] = ('Platform-level coverage attestation does not prove individual application/grant telemetry is complete. '
                                      'Missing coverage is a separate unresolved queue, not automatic approval.')
    if max_results is not None:
        if max_results < 1:
            raise ValueError('max_results must be >= 1')
        result['accounts_truncated'] = len(result['accounts']) > max_results
        result['accounts'] = result['accounts'][:max_results]
    return result
