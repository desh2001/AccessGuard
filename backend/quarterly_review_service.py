"""Quarterly Review Orchestration Service — AccessGuard IGA Lab.

Implements the end-to-end 90-day review lifecycle:
1. Frozen cycle preview & creation.
2. Deterministic policy rules + ML anomaly percentile integration.
3. Reviewer task assignment and human decision recording.
4. Reviewed outcome CSV template generation, upload preview, atomic commit, and export.
5. Offline ML training snapshot preparation with strict label separation.

Strict Guardrails:
- ML never revokes, retains or certfies access.
- Mandatory lifecycle/transfer cases bypass review budget.
- Spare review budget is never filled with random accounts.
- `access_decision=retain` != `review_classification=verified_normal`.
- CSV commit is atomic (zero partial imports on error).
- Uploading CSV never auto-trains or promotes a model.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from models import (
    Identity, System, Account, AccessGrant, ActivityEvent,
    EmployeeTransfer, ADGroupCatalog, ADGroupMembershipHistory,
    QuarterlyReviewCycle, QuarterlyAccountReview,
    ReviewOutcomeImportBatch, ReviewOutcomeImportRow, QuarterlyReviewOutcome,
    MLTrainingRun, AuditLog, now_utc
)
from quarterly_feature_builder import build_account_features, resolve_platform
from ml_client import check_ml_health, score_accounts_batch, get_ml_models

CSV_HEADERS = [
    'schema_version',
    'review_cycle_id',
    'account_id',
    'platform',
    'reviewer_id',
    'reviewed_at_utc',
    'review_classification',
    'access_decision',
    'rationale',
    'evidence_reference',
]

VALID_CLASSIFICATIONS = {
    'verified_normal',
    'confirmed_behavioral_concern',
    'confirmed_policy_concern',
    'insufficient_evidence',
    'not_applicable',
}

VALID_DECISIONS = {
    'retain',
    'request_revoke',
    'request_reduce',
    'defer',
    'escalate',
}


def _csv_escape(val: Any) -> str:
    """Sanitize string against CSV formula injection."""
    if val is None:
        return ''
    s = str(val).strip()
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return f"'{s}"
    return s


# ═══════════════════════════════════════════════════════════════════════════
# 1. CYCLE PREVIEW & CREATION
# ═══════════════════════════════════════════════════════════════════════════

def build_cycle_preview(
    db: Session,
    as_of: datetime | None = None,
    window_days: int = 90,
    budget_pct: int = 10,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Build read-only preview of 90-day quarterly review cycle."""
    as_of = as_of or now_utc()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    window_end = as_of
    window_start = as_of - timedelta(days=window_days)
    cycle_id = cycle_id or f"{as_of.year}-Q{(as_of.month - 1) // 3 + 1}"

    # 1. Aggregate features for all active accounts
    feature_records = build_account_features(db, window_start, window_end)
    total_accounts = len(feature_records)

    # 2. Query ML service (if online)
    ml_health = check_ml_health()
    ml_available = ml_health.get('online', False)
    ml_results = {}
    if ml_available:
        # Only send eligible 90-day records with known coverage to ML
        eligible_for_ml = [
            r for r in feature_records
            if r['features'].get('log_coverage_known') == 1
            and r['features'].get('log_coverage_days', 0) >= 0.995 * window_days
            and r['features'].get('platform', '').lower() in ('windows ad', 'linux', 'github')
        ]
        if eligible_for_ml:
            ml_results = score_accounts_batch(cycle_id, window_days, eligible_for_ml)

    # 3. Apply deterministic policy rules & priorities
    accounts_preview = []
    mandatory_count = 0
    evidence_gap_count = 0
    unscored_platforms_count = 0

    candidate_pool = []

    for item in feature_records:
        acc_id = item['account_id']
        features = item['features']
        internal = item['_internal']
        platform_name = item['platform']

        # Policy score starting at 10
        policy_score = 10
        reasons: list[str] = []
        is_mandatory = False

        # Rule 1: Leaver holding access (Departed employee)
        if internal['identity_status'] == 'Departed':
            policy_score += 50
            reasons.append("Departed identity still holds active access")
            is_mandatory = True

        # Rule 2: Unlinked technical account
        if internal['identity_id'] is None:
            policy_score += 40
            reasons.append("Unlinked technical account — owner identity not verified")
            is_mandatory = True

        # Rule 3: Recent HR transfer / reporting change
        if internal['transfers_count'] > 0:
            policy_score += 35
            reasons.append(f"Internal employee transfer recorded in review window ({internal['transfers_count']} transfers)")
            is_mandatory = True

        # Rule 4: Out-of-scope AD group or policy conflict
        if features.get('out_of_scope_ad_group_count', 0) > 0:
            policy_score += 30
            reasons.append(f"Holds {features['out_of_scope_ad_group_count']} out-of-scope AD groups according to catalog")
            is_mandatory = True

        # Rule 5: Privileged admin permission
        if features.get('privileged_entitlements', 0) > 0:
            policy_score += 23
            reasons.append(f"Holds {features['privileged_entitlements']} privileged administrator entitlements")

        # Rule 6: Telemetry coverage gap
        cov_known = features.get('log_coverage_known', 0)
        cov_days = features.get('log_coverage_days', 0.0)
        if cov_known == 0 or cov_days < (0.995 * window_days):
            reasons.append("Telemetry coverage unverified or incomplete for 90-day window")
            has_coverage_gap = True
        else:
            has_coverage_gap = False

        # Rule 7: Long inactivity (only if coverage is verified)
        if not has_coverage_gap and features.get('resource_use_events_window', 0) == 0:
            policy_score += 23
            reasons.append("No verified resource use observed during 90-day window (coverage verified)")

        policy_score = min(100, policy_score)

        # ML result
        ml_res = ml_results.get(acc_id)
        if ml_res and ml_res.get('status') == 'scored':
            ml_percentile = ml_res.get('anomaly_percentile_100')
            ml_status = 'scored'
            ml_model_key = ml_res.get('model_key')
            ml_model_schema = ml_res.get('model_schema')
            ml_model_trained_utc = ml_res.get('model_trained_utc')
        else:
            ml_percentile = None
            ml_status = ml_res.get('reason') if ml_res else ('coverage_gap' if has_coverage_gap else 'ml_unavailable')
            ml_model_key = None
            ml_model_schema = None
            ml_model_trained_utc = None

        if platform_name not in ('Windows AD', 'Linux', 'GitHub'):
            unscored_platforms_count += 1

        record_entry = {
            'account_id': int(acc_id),
            'username': internal['username'],
            'platform': platform_name,
            'department': features.get('department', 'unknown'),
            'account_type': features.get('account_type', 'unknown'),
            'entitlement_count': internal['entitlement_count'],
            'policy_score': policy_score,
            'policy_reasons': reasons,
            'is_mandatory': is_mandatory,
            'has_coverage_gap': has_coverage_gap,
            'coverage_days': cov_days,
            'coverage_known': cov_known,
            'transfer_flag': 1 if internal['transfers_count'] > 0 else 0,
            'ml_percentile': ml_percentile,
            'ml_status': ml_status,
            'ml_model_key': ml_model_key,
            'ml_model_schema': ml_model_schema,
            'ml_model_trained_utc': ml_model_trained_utc,
            'features': features,
        }

        if is_mandatory:
            record_entry['priority'] = 'mandatory'
            mandatory_count += 1
            accounts_preview.append(record_entry)
        elif has_coverage_gap:
            record_entry['priority'] = 'insufficient_evidence'
            evidence_gap_count += 1
            accounts_preview.append(record_entry)
        else:
            candidate_pool.append(record_entry)

    # 4. Budget selection for non-mandatory candidates
    # Budget target = max(1, total_accounts * budget_pct // 100)
    # Selected pool is ordered by policy score (primary) and ML percentile (tiebreaker)
    max_budget_count = max(1, int((total_accounts * budget_pct) / 100))
    candidate_pool.sort(
        key=lambda r: (r['policy_score'], r['ml_percentile'] or 0.0),
        reverse=True,
    )

    selected_count = 0
    deferred_count = 0
    for idx, cand in enumerate(candidate_pool):
        if idx < max_budget_count and (cand['policy_score'] >= 30 or (cand['ml_percentile'] and cand['ml_percentile'] >= 80.0)):
            cand['priority'] = 'selected'
            selected_count += 1
        else:
            cand['priority'] = 'deferred_candidate'
            deferred_count += 1
        accounts_preview.append(cand)

    # Sort final preview: mandatory first, then selected, then deferred, then insufficient_evidence
    priority_order = {'mandatory': 0, 'selected': 1, 'deferred_candidate': 2, 'insufficient_evidence': 3}
    accounts_preview.sort(key=lambda r: (priority_order.get(r['priority'], 9), -r['policy_score']))

    return {
        'cycle_id': cycle_id,
        'as_of': as_of.isoformat(),
        'window_start': window_start.isoformat(),
        'window_end': window_end.isoformat(),
        'window_days': window_days,
        'review_budget_pct': budget_pct,
        'mode': 'hybrid' if ml_available and len(ml_results) > 0 else 'policy_only',
        'ml_status': ml_health.get('status', 'offline'),
        'total_accounts': total_accounts,
        'mandatory_count': mandatory_count,
        'selected_count': selected_count,
        'deferred_count': deferred_count,
        'evidence_gap_count': evidence_gap_count,
        'unscored_platforms_count': unscored_platforms_count,
        'queue_size': mandatory_count + selected_count,
        'accounts': accounts_preview,
    }


def create_review_cycle(
    db: Session,
    as_of: datetime | None = None,
    window_days: int = 90,
    budget_pct: int = 10,
    cycle_id: str | None = None,
    created_by: str = 'Admin',
) -> QuarterlyReviewCycle:
    """Freeze and persist a quarterly review cycle and its account tasks."""
    preview = build_cycle_preview(db, as_of, window_days, budget_pct, cycle_id)
    cid = preview['cycle_id']

    existing = db.get(QuarterlyReviewCycle, cid)
    if existing:
        raise ValueError(f"Review cycle {cid} already exists")

    as_of_dt = datetime.fromisoformat(preview['as_of'])
    window_start = datetime.fromisoformat(preview['window_start'])
    window_end = datetime.fromisoformat(preview['window_end'])

    models_info = get_ml_models()

    cycle = QuarterlyReviewCycle(
        id=cid,
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        review_budget_pct=budget_pct,
        as_of=as_of_dt,
        created_by=created_by,
        created_at=now_utc(),
        status='created',
        mode=preview['mode'],
        total_accounts=preview['total_accounts'],
        mandatory_count=preview['mandatory_count'],
        selected_count=preview['selected_count'],
        deferred_count=preview['deferred_count'],
        evidence_gap_count=preview['evidence_gap_count'],
        model_versions=json.dumps(models_info.get('models', {})),
        frozen_config=json.dumps({
            'budget_pct': budget_pct,
            'window_days': window_days,
            'mode': preview['mode'],
        }),
    )
    db.add(cycle)
    db.flush()

    for acc in preview['accounts']:
        task = QuarterlyAccountReview(
            cycle_id=cid,
            account_id=acc['account_id'],
            platform=acc['platform'],
            priority=acc['priority'],
            policy_score=acc['policy_score'],
            policy_reasons=json.dumps(acc['policy_reasons']),
            ml_percentile=acc['ml_percentile'],
            ml_status=acc['ml_status'],
            ml_model_key=acc['ml_model_key'],
            ml_model_schema=acc['ml_model_schema'],
            ml_model_trained_utc=acc['ml_model_trained_utc'],
            coverage_days=acc['coverage_days'],
            coverage_known=acc['coverage_known'],
            transfer_flag=acc['transfer_flag'],
            reason_codes=json.dumps(acc['policy_reasons']),
            state='pending',
        )
        db.add(task)

    db.add(AuditLog(
        created_at=now_utc(),
        actor=created_by,
        action='QUARTERLY_CYCLE_CREATED',
        entity=f'QuarterlyReviewCycle:{cid}',
        details=(
            f"Created cycle {cid} with {preview['total_accounts']} accounts. "
            f"Mandatory: {preview['mandatory_count']}, Selected: {preview['selected_count']}, "
            f"Deferred: {preview['deferred_count']}, Mode: {preview['mode']}."
        ),
    ))
    db.commit()
    return cycle


# ═══════════════════════════════════════════════════════════════════════════
# 2. REVIEW DECISIONS
# ═══════════════════════════════════════════════════════════════════════════

def record_account_decision(
    db: Session,
    task_id: int,
    decision: str,
    reviewer_id: str,
    rationale: str,
) -> QuarterlyAccountReview:
    """Record human reviewer decision for a quarterly review task."""
    task = db.get(QuarterlyAccountReview, task_id)
    if not task:
        raise ValueError(f"Account review task {task_id} not found")

    decision_clean = decision.strip().lower()
    if decision_clean not in VALID_DECISIONS:
        raise ValueError(f"Invalid access decision: {decision}. Must be one of {sorted(VALID_DECISIONS)}")

    rationale_clean = rationale.strip()
    if not rationale_clean:
        raise ValueError("Rationale is mandatory and cannot be empty")

    reviewer_clean = reviewer_id.strip()
    if not reviewer_clean:
        raise ValueError("Reviewer ID is required")

    task.decision = decision_clean
    task.decision_by = reviewer_clean
    task.decision_at = now_utc()
    task.decision_rationale = rationale_clean
    task.state = 'decided'

    db.add(AuditLog(
        created_at=now_utc(),
        actor=reviewer_clean,
        action=f"REVIEW_DECISION_{decision_clean.upper()}",
        entity=f"QuarterlyAccountReview:{task_id}",
        details=f"Account {task.account_id} in cycle {task.cycle_id}: decision={decision_clean}, rationale={rationale_clean}",
    ))
    db.commit()
    return task


# ═══════════════════════════════════════════════════════════════════════════
# 3. CSV TEMPLATE GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_outcome_template_csv(
    db: Session,
    cycle_id: str,
    scope: str = 'review_queue',
) -> str:
    """Generate blank review-outcome CSV template for an operational cycle or pilot."""
    cycle = db.get(QuarterlyReviewCycle, cycle_id)
    if not cycle:
        raise ValueError(f"Cycle {cycle_id} not found")

    query = select(QuarterlyAccountReview).where(QuarterlyAccountReview.cycle_id == cycle_id)
    if scope == 'review_queue':
        query = query.where(QuarterlyAccountReview.priority.in_(['mandatory', 'selected']))
    tasks = db.scalars(query.order_by(QuarterlyAccountReview.id.asc())).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADERS)

    for t in tasks:
        acc = db.get(Account, t.account_id)
        platform_key = resolve_platform(acc.system) if acc and acc.system else 'unknown'
        writer.writerow([
            1,                  # schema_version
            cycle_id,           # review_cycle_id
            f"ACC-{t.account_id}", # account_id opaque format
            platform_key,       # platform
            '',                 # reviewer_id (to be filled)
            '',                 # reviewed_at_utc (to be filled)
            '',                 # review_classification (to be filled)
            '',                 # access_decision (to be filled)
            '',                 # rationale (to be filled)
            '',                 # evidence_reference (optional)
        ])

    return output.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 4. CSV UPLOAD PREVIEW & ATOMIC COMMIT
# ═══════════════════════════════════════════════════════════════════════════

def _parse_account_id(raw: str) -> int | None:
    raw = raw.strip()
    if raw.startswith('ACC-'):
        raw = raw[4:]
    try:
        return int(raw)
    except ValueError:
        return None


def preview_outcome_csv(
    db: Session,
    cycle_id: str,
    file_bytes: bytes,
    original_filename: str,
    uploader: str,
    scope: str = 'full_population',
) -> dict[str, Any]:
    """Parse, stage and validate a reviewed-outcomes CSV file.

    Zero mutations to final outcomes or models during preview.
    """
    cycle = db.get(QuarterlyReviewCycle, cycle_id)
    if not cycle:
        raise ValueError(f"Cycle {cycle_id} not found")

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # UTF-8 with BOM tolerance
    try:
        text = file_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_bytes.decode('utf-8', errors='replace')

    # Read CSV
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("Uploaded CSV file is completely empty")

    header_clean = [h.strip().lower() for h in header]
    if header_clean != CSV_HEADERS:
        raise ValueError(f"Invalid CSV header. Expected exactly:\n{CSV_HEADERS}\nFound:\n{header_clean}")

    batch_id = f"batch-{cycle_id}-{now_utc().strftime('%Y%m%d%H%M%S')}-{file_hash[:8]}"
    batch = ReviewOutcomeImportBatch(
        id=batch_id,
        cycle_id=cycle_id,
        original_filename=re.sub(r'[^a-zA-Z0-9_.-]', '_', original_filename)[:250],
        file_sha256=file_hash,
        uploader=uploader,
        uploaded_at=now_utc(),
        schema_version=1,
        template_scope=scope,
        status='previewed',
    )
    db.add(batch)
    db.flush()

    total_rows = 0
    valid_rows = 0
    invalid_rows = 0
    duplicate_rows = 0
    unknown_accounts = 0
    platform_mismatches = 0
    errors: list[dict[str, Any]] = []

    seen_account_ids: set[int] = set()

    # Pre-fetch existing accounts for validation
    account_cache = {a.id: a for a in db.scalars(select(Account)).all()}
    existing_outcomes = set(db.scalars(
        select(QuarterlyReviewOutcome.account_id).where(QuarterlyReviewOutcome.cycle_id == cycle_id)
    ).all())

    # All expected accounts in cycle (for full_population check)
    cycle_account_ids = set(db.scalars(
        select(QuarterlyAccountReview.account_id).where(QuarterlyAccountReview.cycle_id == cycle_id)
    ).all())

    for row_idx, row in enumerate(reader, start=2):
        total_rows += 1
        if len(row) < 9:
            err = {'row_number': row_idx, 'field': 'row', 'code': 'incomplete_row', 'message': f"Row has only {len(row)} columns, expected at least 9"}
            errors.append(err)
            invalid_rows += 1
            db.add(ReviewOutcomeImportRow(batch_id=batch_id, csv_row_number=row_idx, is_valid=0, error_code='incomplete_row', error_message=err['message']))
            continue

        raw_version, raw_cycle, raw_acc, raw_plat, raw_rev, raw_ts, raw_class, raw_dec, raw_rat = [c.strip() for c in row[:9]]
        raw_ref = row[9].strip() if len(row) > 9 else ''

        row_errors = []

        # Validate schema version
        if raw_version != '1':
            row_errors.append(('schema_version', 'unsupported_schema_version', f"Schema version must be 1, found '{raw_version}'"))

        # Validate cycle id
        if raw_cycle != cycle_id:
            row_errors.append(('review_cycle_id', 'cycle_mismatch', f"Row review_cycle_id '{raw_cycle}' does not match upload cycle '{cycle_id}'"))

        # Validate account id
        acc_id = _parse_account_id(raw_acc)
        if acc_id is None or acc_id not in account_cache:
            row_errors.append(('account_id', 'unknown_account', f"Account ID '{raw_acc}' not found in database"))
            unknown_accounts += 1
        elif acc_id in seen_account_ids:
            row_errors.append(('account_id', 'duplicate_in_file', f"Duplicate account ID '{raw_acc}' within this file"))
            duplicate_rows += 1
        elif acc_id in existing_outcomes:
            row_errors.append(('account_id', 'already_reviewed', f"Account ID '{raw_acc}' already has committed outcome in cycle {cycle_id}"))
            duplicate_rows += 1
        else:
            seen_account_ids.add(acc_id)
            # Validate platform matches account's system platform
            acc_obj = account_cache[acc_id]
            expected_plat = resolve_platform(acc_obj.system) if acc_obj and acc_obj.system else 'unknown'
            if raw_plat.lower() not in (expected_plat, 'unknown', 'windows ad', 'linux host'):
                row_errors.append(('platform', 'platform_mismatch', f"Platform '{raw_plat}' does not match account system platform '{expected_plat}'"))
                platform_mismatches += 1

        # Validate reviewer id
        if not raw_rev:
            row_errors.append(('reviewer_id', 'missing_reviewer', "reviewer_id is mandatory"))

        # Validate timestamp
        try:
            ts_str = raw_ts.replace('Z', '+00:00')
            parsed_dt = datetime.fromisoformat(ts_str)
        except Exception:
            row_errors.append(('reviewed_at_utc', 'invalid_timestamp', f"Invalid ISO-8601 UTC timestamp: '{raw_ts}'"))

        # Validate classification
        clean_class = raw_class.lower()
        if clean_class not in VALID_CLASSIFICATIONS:
            row_errors.append(('review_classification', 'invalid_classification', f"Invalid classification '{raw_class}'. Must be one of {sorted(VALID_CLASSIFICATIONS)}"))

        # Validate access decision
        clean_dec = raw_dec.lower()
        if clean_dec not in VALID_DECISIONS:
            row_errors.append(('access_decision', 'invalid_decision', f"Invalid access decision '{raw_dec}'. Must be one of {sorted(VALID_DECISIONS)}"))

        # Validate rationale
        if not raw_rat:
            row_errors.append(('rationale', 'missing_rationale', "rationale is mandatory"))

        is_valid = 1 if len(row_errors) == 0 else 0
        if is_valid:
            valid_rows += 1
            db.add(ReviewOutcomeImportRow(
                batch_id=batch_id,
                csv_row_number=row_idx,
                account_id=str(acc_id),
                platform=raw_plat,
                reviewer_id=raw_rev,
                reviewed_at_utc=raw_ts,
                review_classification=clean_class,
                access_decision=clean_dec,
                rationale=raw_rat,
                evidence_reference=raw_ref or None,
                is_valid=1,
            ))
        else:
            invalid_rows += 1
            for field, code, msg in row_errors:
                errors.append({'row_number': row_idx, 'field': field, 'code': code, 'message': msg})
            first_code = row_errors[0][1]
            first_msg = row_errors[0][2]
            db.add(ReviewOutcomeImportRow(
                batch_id=batch_id,
                csv_row_number=row_idx,
                account_id=raw_acc,
                platform=raw_plat,
                reviewer_id=raw_rev,
                reviewed_at_utc=raw_ts,
                review_classification=clean_class,
                access_decision=clean_dec,
                rationale=raw_rat,
                evidence_reference=raw_ref or None,
                is_valid=0,
                error_code=first_code,
                error_message=first_msg,
            ))

    # Missing population accounts check (for full_population scope)
    missing_accounts = len(cycle_account_ids - seen_account_ids)

    can_commit = (invalid_rows == 0 and duplicate_rows == 0 and total_rows > 0 and len(errors) == 0)

    batch.total_rows = total_rows
    batch.valid_rows = valid_rows
    batch.invalid_rows = invalid_rows
    batch.duplicate_rows = duplicate_rows
    batch.validation_summary = json.dumps({
        'can_commit': can_commit,
        'missing_population_accounts': missing_accounts,
        'platform_mismatches': platform_mismatches,
        'unknown_accounts': unknown_accounts,
    })
    db.commit()

    return {
        'batch_id': batch_id,
        'cycle_id': cycle_id,
        'status': 'previewed',
        'scope': scope,
        'total_rows': total_rows,
        'valid_rows': valid_rows,
        'invalid_rows': invalid_rows,
        'duplicate_rows': duplicate_rows,
        'unknown_account_rows': unknown_accounts,
        'wrong_platform_rows': platform_mismatches,
        'missing_population_accounts': missing_accounts,
        'can_commit': can_commit,
        'errors': errors[:50],  # Return up to first 50 row errors
    }


def commit_outcome_batch(
    db: Session,
    batch_id: str,
    approver: str,
) -> dict[str, Any]:
    """Atomically commit a validated review-outcome batch.

    All-or-nothing: zero writes on any error.
    """
    batch = db.get(ReviewOutcomeImportBatch, batch_id)
    if not batch:
        raise ValueError(f"Batch {batch_id} not found")

    if batch.status == 'committed':
        return {
            'status': 'already_committed',
            'batch_id': batch_id,
            'committed_at': batch.committed_at.isoformat() if batch.committed_at else None,
            'records_committed': batch.valid_rows,
        }

    if batch.status != 'previewed':
        raise ValueError(f"Cannot commit batch in status '{batch.status}'")

    if batch.invalid_rows > 0 or batch.duplicate_rows > 0:
        raise ValueError(f"Batch has {batch.invalid_rows} invalid and {batch.duplicate_rows} duplicate rows; cannot commit")

    rows = db.scalars(
        select(ReviewOutcomeImportRow).where(
            ReviewOutcomeImportRow.batch_id == batch_id,
            ReviewOutcomeImportRow.is_valid == 1
        ).order_by(ReviewOutcomeImportRow.csv_row_number.asc())
    ).all()

    if len(rows) != batch.valid_rows:
        raise ValueError("Staged valid rows count mismatch; aborting commit")

    # Atomic commit
    committed_count = 0
    for r in rows:
        acc_id = int(r.account_id)
        # Parse timestamp
        ts_str = r.reviewed_at_utc.replace('Z', '+00:00')
        rev_dt = datetime.fromisoformat(ts_str)

        outcome = QuarterlyReviewOutcome(
            cycle_id=batch.cycle_id,
            account_id=acc_id,
            platform=r.platform or 'unknown',
            reviewer_id=r.reviewer_id,
            reviewed_at_utc=rev_dt,
            review_classification=r.review_classification,
            access_decision=r.access_decision,
            rationale=r.rationale,
            evidence_reference=r.evidence_reference,
            import_batch_id=batch_id,
            uploader=batch.uploader,
            approved_by=approver,
            approved_at=now_utc(),
        )
        db.add(outcome)

        # Update QuarterlyAccountReview if present
        review_task = db.scalar(
            select(QuarterlyAccountReview).where(
                QuarterlyAccountReview.cycle_id == batch.cycle_id,
                QuarterlyAccountReview.account_id == acc_id
            )
        )
        if review_task:
            review_task.state = 'decided'
            review_task.decision = r.access_decision
            review_task.decision_by = r.reviewer_id
            review_task.decision_at = rev_dt
            review_task.decision_rationale = r.rationale

        committed_count += 1

    batch.status = 'committed'
    batch.committed_at = now_utc()

    db.add(AuditLog(
        created_at=now_utc(),
        actor=approver,
        action='REVIEW_OUTCOMES_COMMITTED',
        entity=f'ReviewOutcomeImportBatch:{batch_id}',
        details=f"Committed {committed_count} manual review outcomes for cycle {batch.cycle_id} from file {batch.original_filename}.",
    ))

    db.commit()

    return {
        'status': 'committed',
        'batch_id': batch_id,
        'cycle_id': batch.cycle_id,
        'records_committed': committed_count,
        'committed_at': batch.committed_at.isoformat(),
    }


def export_committed_outcomes_csv(
    db: Session,
    cycle_id: str,
) -> str:
    """Audit export of all accepted review outcomes with safe CSV escaping."""
    outcomes = db.scalars(
        select(QuarterlyReviewOutcome).where(QuarterlyReviewOutcome.cycle_id == cycle_id).order_by(QuarterlyReviewOutcome.id.asc())
    ).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        'cycle_id',
        'account_id',
        'platform',
        'reviewer_id',
        'reviewed_at_utc',
        'review_classification',
        'access_decision',
        'rationale',
        'evidence_reference',
        'import_batch_id',
        'approved_by',
        'approved_at',
    ])

    for o in outcomes:
        writer.writerow([
            _csv_escape(o.cycle_id),
            _csv_escape(f"ACC-{o.account_id}"),
            _csv_escape(o.platform),
            _csv_escape(o.reviewer_id),
            _csv_escape(o.reviewed_at_utc.isoformat()),
            _csv_escape(o.review_classification),
            _csv_escape(o.access_decision),
            _csv_escape(o.rationale),
            _csv_escape(o.evidence_reference or ''),
            _csv_escape(o.import_batch_id or ''),
            _csv_escape(o.approved_by or ''),
            _csv_escape(o.approved_at.isoformat() if o.approved_at else ''),
        ])

    return output.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 5. OFFLINE ML TRAINING PREPARATION
# ═══════════════════════════════════════════════════════════════════════════

def get_training_readiness(db: Session, platform: str) -> dict[str, Any]:
    """Calculate counts of approved reviewed outcomes available for candidate training."""
    canonical_plat = resolve_platform(System(id=platform, name=platform, category='')) or platform.lower()
    
    query = select(QuarterlyReviewOutcome).where(
        QuarterlyReviewOutcome.platform.ilike(f"%{canonical_plat}%")
    )
    outcomes = db.scalars(query).all()

    normal_count = sum(1 for o in outcomes if o.review_classification == 'verified_normal')
    behavioral_count = sum(1 for o in outcomes if o.review_classification == 'confirmed_behavioral_concern')
    policy_count = sum(1 for o in outcomes if o.review_classification == 'confirmed_policy_concern')
    insufficient_count = sum(1 for o in outcomes if o.review_classification == 'insufficient_evidence')
    na_count = sum(1 for o in outcomes if o.review_classification == 'not_applicable')

    # Requirements from platform_train.py: need >=65 baseline normal and >=120 total records
    has_minimum_normal = normal_count >= 65
    has_minimum_total = (normal_count + behavioral_count) >= 120

    return {
        'platform': canonical_plat,
        'total_reviewed_outcomes': len(outcomes),
        'verified_normal': normal_count,
        'confirmed_behavioral_concern': behavioral_count,
        'confirmed_policy_concern': policy_count,
        'insufficient_evidence': insufficient_count,
        'not_applicable': na_count,
        'eligible_for_normal_training': normal_count,
        'held_out_for_evaluation': behavioral_count,
        'has_minimum_normal_records': has_minimum_normal,
        'has_minimum_total_records': has_minimum_total,
        'can_prepare_candidate': has_minimum_normal,
        'minimum_normal_required': 65,
        'minimum_total_required': 120,
    }


def prepare_training_candidate_snapshot(
    db: Session,
    platform: str,
    created_by: str,
    cycle_ids: list[str] | None = None,
) -> MLTrainingRun:
    """Prepare a frozen dataset snapshot record for offline model training.

    Guarantees:
    - Never calls .fit() during request.
    - Strict label separation (verified_normal -> label=0, confirmed_behavioral_concern -> label=1).
    - Policy concerns, insufficient evidence, and access decisions are excluded.
    """
    readiness = get_training_readiness(db, platform)
    if not readiness['can_prepare_candidate']:
        raise ValueError(
            f"Insufficient baseline normal records for {platform}. "
            f"Have {readiness['verified_normal']}, need >= {readiness['minimum_normal_required']} verified_normal outcomes."
        )

    run_id = f"train-run-{platform}-{now_utc().strftime('%Y%m%d%H%M%S')}"
    run = MLTrainingRun(
        id=run_id,
        platform=platform,
        status='prepared',
        model_schema='aegis-v8-quarterly-platform-specific-1',
        feature_schema_version='v10-platform-features',
        source_cycle_ids=json.dumps(cycle_ids or ['all']),
        training_normal_count=readiness['verified_normal'],
        training_concern_count=readiness['confirmed_behavioral_concern'],
        created_by=created_by,
        created_at=now_utc(),
        validation_report=json.dumps({
            'readiness': readiness,
            'note': 'Prepared frozen dataset snapshot for offline training. Run platform_train CLI to build candidate model.'
        }),
    )
    db.add(run)
    db.add(AuditLog(
        created_at=now_utc(),
        actor=created_by,
        action='TRAINING_CANDIDATE_PREPARED',
        entity=f'MLTrainingRun:{run_id}',
        details=f"Prepared candidate dataset snapshot for {platform}: {readiness['verified_normal']} normal records, {readiness['confirmed_behavioral_concern']} evaluation records.",
    ))
    db.commit()
    return run
