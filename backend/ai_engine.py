"""Enhanced AI engine — IsolationForest anomaly ranking + peer-group analysis.

Research prototype only. Scores are relative to the CURRENT synthetic cohort.
They are NOT calibrated probabilities, NOT evidence of wrongdoing,
and NOT grounds for automatic revocation without human review.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
import numpy as np
from sklearn.ensemble import IsolationForest
from risk import parse_time, risk_level

# Feature names for transparency
FEATURES = [
    'privileged',           # Admin/root permission flag
    'cross_department',     # Access outside expected department
    'departed_owner',       # Identity marked Departed
    'unlinked_owner',       # No identity linked to account
    'days_since_verified_use',  # Normalised 0–1 (max 365 days)
    'use_evidence_missing', # 1 if no activity log entry at all
    'role_rarity',          # 1/count of same (dept, system, permission) triples
    'peer_privilege_gap',   # 1 if Admin but most peers in dept are not
]


def _days_since(value: Any) -> int:
    dt = parse_time(value)
    if dt is None:
        return 0
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _build_peer_index(active: list[dict]) -> dict:
    """For each department, count the fraction of Admin grants."""
    dept_counts: dict[str, dict] = defaultdict(lambda: {'total': 0, 'admin': 0})
    for row in active:
        dept = row.get('department', 'Unknown')
        dept_counts[dept]['total'] += 1
        if row.get('privilege'):
            dept_counts[dept]['admin'] += 1
    # Fraction of Admin in each department
    return {
        dept: v['admin'] / max(1, v['total'])
        for dept, v in dept_counts.items()
    }


def _vector(row: dict, role_counts: Counter, peer_admin_frac: dict) -> list[float]:
    last = parse_time(row.get('last_verified_use'))
    age = _days_since(row.get('last_verified_use'))
    role_key = (row.get('department'), row.get('system_id'), row.get('permission'))
    rarity = 1.0 / max(1, role_counts[role_key])
    dept = row.get('department', 'Unknown')
    admin_frac = peer_admin_frac.get(dept, 0.0)
    peer_gap = 1.0 if (row.get('privilege') and admin_frac < 0.25) else 0.0
    return [
        float(bool(row.get('privilege'))),
        float(bool(row.get('cross_department'))),
        float(row.get('status') == 'Departed'),
        float(row.get('identity_id') is None),
        min(365, age) / 365.0,
        float(last is None),
        float(rarity),
        float(peer_gap),
    ]


def _recommendation(combined: int, rule: int) -> str:
    if combined >= 75 or rule >= 85:
        return 'Escalate for urgent review'
    if combined >= 60 or rule >= 60:
        return 'Request human review'
    return 'Monitor'


def rank_anomalies(rows: list[dict]) -> dict:
    """Rank active grants by combined rule-score + IsolationForest anomaly percentile.

    Returns both the baseline rule scores (never suppressed) and the ML ranking.
    """
    active = [r for r in rows if r.get('grant_status') == 'Active']

    if len(active) < 10:
        return {
            'mode': 'insufficient-data',
            'samples': len(active),
            'message': 'At least 10 active grants required for ML ranking; deterministic rules remain available.',
            'findings': [],
        }

    role_counts = Counter(
        (r.get('department'), r.get('system_id'), r.get('permission'))
        for r in active
    )
    peer_admin_frac = _build_peer_index(active)
    X = np.asarray(
        [_vector(r, role_counts, peer_admin_frac) for r in active], dtype=float
    )

    # Train IsolationForest on current cohort
    contamination = min(0.15, max(0.05, sum(1 for r in active if r.get('risk_score', 0) >= 60) / len(active)))
    model = IsolationForest(
        n_estimators=150,
        contamination=contamination,
        random_state=42,
        max_samples='auto',
    )
    model.fit(X)
    raw_scores = -model.decision_function(X)  # higher = more anomalous

    # Convert to percentile rank within cohort
    rank_order = np.argsort(np.argsort(raw_scores, kind='stable'), kind='stable')
    denom = max(1, len(active) - 1)

    findings = []
    for i, row in enumerate(active):
        percentile = round(100 * float(rank_order[i]) / denom)
        rule_score = int(row.get('risk_score', 0))
        # Blended: 70% rule-based (explainable) + 30% ML anomaly
        combined = round(0.70 * rule_score + 0.30 * percentile)
        reasons = list(row.get('reasons', []))
        if not reasons:
            reasons = ['Unusual feature combination relative to current synthetic cohort']
        evidence_quality = (
            'Missing' if row.get('last_verified_use') is None
            else 'Partial (synthetic log coverage only)'
        )
        findings.append({
            'grant_id': row['id'],
            'identity_name': row.get('identity_name', 'Unknown'),
            'system_name': row.get('system_name', 'Unknown'),
            'permission': row.get('permission', 'Unknown'),
            'department': row.get('department', 'Unmapped'),
            'rule_score': rule_score,
            'rule_level': risk_level(rule_score),
            'anomaly_percentile': percentile,
            'combined_priority': combined,
            'combined_level': risk_level(combined),
            'reasons': reasons,
            'evidence_quality': evidence_quality,
            'recommendation': _recommendation(combined, rule_score),
            'peer_admin_fraction': round(peer_admin_frac.get(row.get('department', ''), 0), 2),
            'model': 'IsolationForest (research prototype)',
        })

    findings.sort(key=lambda r: (r['combined_priority'], r['rule_score']), reverse=True)

    # Summary stats
    urgent = sum(1 for f in findings if f['recommendation'] == 'Escalate for urgent review')
    review = sum(1 for f in findings if f['recommendation'] == 'Request human review')

    return {
        'mode': 'trained-on-current-cohort',
        'samples': len(active),
        'features': FEATURES,
        'algorithm': 'IsolationForest',
        'contamination_used': round(contamination, 3),
        'summary': {
            'urgent': urgent,
            'needs_review': review,
            'monitor': len(findings) - urgent - review,
        },
        'metric_note': (
            'Percentiles measure unusualness within this synthetic cohort ONLY. '
            'They are NOT attack probabilities, NOT ground-truth validated, '
            'and NOT grounds for automatic revocation.'
        ),
        'findings': findings,
    }
