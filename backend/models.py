"""Phase 2 canonical identity and technical-account schema.

Quarterly ML V10: adds normalized event provenance, coverage attestations,
AD group governance, HR transfer history, managed-resource policies,
identity resolution quarantine, quarterly review cycles, review outcomes,
CSV import batches and ML training provenance.
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════════════════
# EXISTING CORE TABLES (preserved for compatibility)
# ═══════════════════════════════════════════════════════════════════════════

class Identity(Base):
    __tablename__ = 'identities'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    manager: Mapped[str] = mapped_column(String(120), nullable=False)
    accounts: Mapped[list[Account]] = relationship(back_populates='identity')
    __table_args__ = (
        CheckConstraint("type IN ('Human','Machine','Vendor')", name='identity_type_valid'),
        CheckConstraint("status IN ('Active','Departed')", name='identity_status_valid'),
    )


class System(Base):
    __tablename__ = 'systems'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    # V10: controlled platform mapping (windows, linux, github, or null for unsupported)
    platform: Mapped[str | None] = mapped_column(String(30), nullable=True)


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_id: Mapped[str | None] = mapped_column(ForeignKey('identities.id', ondelete='SET NULL'), index=True, nullable=True)
    system_id: Mapped[str] = mapped_column(ForeignKey('systems.id'), index=True, nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='Active')
    source: Mapped[str] = mapped_column(String(30), nullable=False, default='DemoSeed')
    mapping_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    # V10: stable platform-native identifier (SID, UID, GitHub numeric ID)
    native_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    native_id_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    identity: Mapped[Identity | None] = relationship(back_populates='accounts')
    system: Mapped[System] = relationship()
    grants: Mapped[list[AccessGrant]] = relationship(back_populates='account')
    __table_args__ = (
        UniqueConstraint('system_id', 'external_account_id', name='uq_account_system_external_id'),
        CheckConstraint("status IN ('Active','Disabled')", name='account_status_valid'),
    )


class AccessGrant(Base):
    __tablename__ = 'access_grants'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'), index=True, nullable=False)
    permission: Mapped[str] = mapped_column(String(80), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    privilege: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cross_department: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_verified_use: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='Active', nullable=False)
    # V10: sensitivity tier for managed-resource policy alignment
    sensitivity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    account: Mapped[Account] = relationship(back_populates='grants')
    __table_args__ = (CheckConstraint("status IN ('Active','Revoked')", name='grant_status_valid'),)


class Review(Base):
    """Legacy grant-level review (kept for backward compatibility)."""
    __tablename__ = 'reviews'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey('access_grants.id'), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='Pending', nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('Pending','Approved','Retained','Remediated')", name='review_status_valid'),)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(180), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)


class ActivityEvent(Base):
    """Normalized activity evidence with V10 provenance fields.

    Absence of events is NOT proof of unused access.
    """
    __tablename__ = 'activity_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'), index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(70), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default='DemoSeed')
    # V10 provenance additions
    source_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("outcome IN ('Success','Failure')", name='activity_outcome_valid'),
        UniqueConstraint('source', 'source_event_id', name='uq_activity_source_event'),
        Index('ix_activity_event_type_occurred', 'event_type', 'occurred_at'),
    )


class ConnectorRun(Base):
    """Source-of-truth import provenance; not proof that a connector has complete coverage."""
    __tablename__ = 'connector_runs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    records_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default='')


# ═══════════════════════════════════════════════════════════════════════════
# V10: QUARTERLY ML INTEGRATION TABLES
# ═══════════════════════════════════════════════════════════════════════════

class ActivityCoverage(Base):
    """Explicit telemetry coverage attestation for a platform/source/event-type.

    Coverage is never inferred from event counts or connector success alone.
    """
    __tablename__ = 'activity_coverage'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey('accounts.id'), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_complete: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    attested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    connector_run_id: Mapped[int | None] = mapped_column(ForeignKey('connector_runs.id'), nullable=True)
    __table_args__ = (
        CheckConstraint("is_complete IN (0, 1)", name='coverage_complete_flag'),
        Index('ix_coverage_platform_dates', 'platform', 'start_at', 'end_at'),
    )


class ADGroupCatalog(Base):
    """Organization-scoped AD group governance catalog.

    Never infer privilege from display name. Unknown mappings remain unknown.
    """
    __tablename__ = 'ad_group_catalog'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(60), nullable=False, default='default')
    directory_id: Mapped[str] = mapped_column(String(120), nullable=False)
    group_key: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_relevance: Mapped[str] = mapped_column(String(30), nullable=False, default='unknown')
    privilege_tier: Mapped[str | None] = mapped_column(String(30), nullable=True)
    allowed_departments: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approver: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint('org_id', 'directory_id', 'group_key', name='uq_ad_group_catalog'),
        CheckConstraint("access_relevance IN ('access','non_access','unknown')", name='ad_group_relevance_valid'),
    )


class ADGroupMembershipHistory(Base):
    """AD group membership tracking with observation times."""
    __tablename__ = 'ad_group_membership_history'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey('identities.id'), index=True, nullable=False)
    org_id: Mapped[str] = mapped_column(String(60), nullable=False, default='default')
    directory_id: Mapped[str] = mapped_column(String(120), nullable=False)
    group_key: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)


class EmployeeTransfer(Base):
    """HR transfer history. Transfers create mandatory review obligations.

    If HR transfer data is unavailable, mark transfer_history_known=0.
    """
    __tablename__ = 'employee_transfers'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey('identities.id'), index=True, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    from_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    from_manager: Mapped[str | None] = mapped_column(String(120), nullable=True)
    to_manager: Mapped[str | None] = mapped_column(String(120), nullable=True)
    from_org_unit: Mapped[str | None] = mapped_column(String(120), nullable=True)
    to_org_unit: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='pending', nullable=False)
    reviewer_disposition: Mapped[str | None] = mapped_column(String(80), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('pending','acknowledged','reviewed','dismissed')", name='transfer_status_valid'),
    )


class ManagedResourcePolicy(Base):
    """Organization-approved business resource policies.

    Only managed, approved resources should be matched against this policy.
    Personal browsing/media/unknown URLs must not be risk signals.
    """
    __tablename__ = 'managed_resource_policies'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    permitted_departments: Mapped[str | None] = mapped_column(Text, nullable=True)
    permitted_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(30), default='standard', nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActivityQuarantine(Base):
    """Unresolved/unmatched events kept for explicit mapping resolution.

    Never attach quarantined events to a guessed account.
    """
    __tablename__ = 'activity_quarantine'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    native_actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action: Mapped[str | None] = mapped_column(String(70), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        Index('ix_quarantine_source_event', 'source', 'source_event_id'),
    )


# ─── Quarterly Review Cycle ──────────────────────────────────────────────

class QuarterlyReviewCycle(Base):
    """Frozen quarterly review cycle metadata and provenance."""
    __tablename__ = 'quarterly_review_cycles'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    review_budget_pct: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='created', nullable=False)
    mode: Mapped[str] = mapped_column(String(30), default='hybrid', nullable=False)
    total_accounts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mandatory_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deferred_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_gap_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_versions: Mapped[str | None] = mapped_column(Text, nullable=True)
    frozen_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint(
            "status IN ('preview','created','in_review','closed','archived')",
            name='cycle_status_valid',
        ),
        CheckConstraint(
            "mode IN ('hybrid','policy_only','ml_unavailable')",
            name='cycle_mode_valid',
        ),
    )


class QuarterlyAccountReview(Base):
    """Per-account quarterly review task. ML never changes decisions."""
    __tablename__ = 'quarterly_account_reviews'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey('quarterly_review_cycles.id'), index=True, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'), index=True, nullable=False)
    platform: Mapped[str | None] = mapped_column(String(30), nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default='deferred_candidate', nullable=False)
    policy_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    policy_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    ml_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    ml_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    ml_model_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ml_model_schema: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ml_model_trained_utc: Mapped[str | None] = mapped_column(String(60), nullable=True)
    coverage_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_known: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transfer_flag: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(30), default='pending', nullable=False)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint('cycle_id', 'account_id', name='uq_quarterly_review_cycle_account'),
        CheckConstraint(
            "priority IN ('mandatory','selected','deferred_candidate','insufficient_evidence','deprioritized_not_certified')",
            name='review_priority_valid',
        ),
        CheckConstraint(
            "state IN ('pending','in_review','decided','closed')",
            name='review_state_valid',
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('retain','request_revoke','request_reduce','revoke_request','reduce_access_request','defer','escalate')",
            name='review_decision_valid',
        ),
    )


# ─── Review Outcome CSV Import ───────────────────────────────────────────

class ReviewOutcomeImportBatch(Base):
    """Tracks CSV upload batches for manual review outcomes."""
    __tablename__ = 'review_outcome_import_batches'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey('quarterly_review_cycles.id'), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploader: Mapped[str] = mapped_column(String(120), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    template_scope: Mapped[str] = mapped_column(String(30), default='review_queue', nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='previewed', nullable=False)
    validation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint(
            "status IN ('previewed','rejected','committed','expired')",
            name='import_batch_status_valid',
        ),
        CheckConstraint(
            "template_scope IN ('full_population','review_queue')",
            name='import_scope_valid',
        ),
    )


class ReviewOutcomeImportRow(Base):
    """Staging table for parsed CSV rows before commit."""
    __tablename__ = 'review_outcome_import_rows'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('review_outcome_import_batches.id'), index=True, nullable=False)
    csv_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at_utc: Mapped[str | None] = mapped_column(String(60), nullable=True)
    review_classification: Mapped[str | None] = mapped_column(String(60), nullable=True)
    access_decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_valid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class QuarterlyReviewOutcome(Base):
    """Final committed manual review outcome per (cycle, account)."""
    __tablename__ = 'quarterly_review_outcomes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey('quarterly_review_cycles.id'), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'), nullable=False)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reviewed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_classification: Mapped[str] = mapped_column(String(60), nullable=False)
    access_decision: Mapped[str] = mapped_column(String(40), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey('review_outcome_import_batches.id'), nullable=True)
    uploader: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        UniqueConstraint('cycle_id', 'account_id', name='uq_review_outcome_cycle_account'),
        CheckConstraint(
            "review_classification IN ('verified_normal','confirmed_behavioral_concern',"
            "'confirmed_policy_concern','insufficient_evidence','not_applicable')",
            name='outcome_classification_valid',
        ),
        CheckConstraint(
            "access_decision IN ('retain','request_revoke','request_reduce','defer','escalate')",
            name='outcome_decision_valid',
        ),
    )


# ─── ML Training Provenance ──────────────────────────────────────────────

class MLTrainingRun(Base):
    """Tracks offline model training runs and candidate/live artifact lifecycle."""
    __tablename__ = 'ml_training_runs'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='prepared', nullable=False)
    model_schema: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_cycle_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_normal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    training_concern_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validation_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_target: Mapped[str | None] = mapped_column(String(60), nullable=True)
    __table_args__ = (
        CheckConstraint(
            "status IN ('prepared','training','trained','validated','approved','promoted','rolled_back','failed')",
            name='training_run_status_valid',
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST ENVIRONMENT / SIMULATOR SCENARIO TABLES
# ═══════════════════════════════════════════════════════════════════════════

class TestScenarioResult(Base):
    """Execution results for automated built-in simulator security scenarios."""
    __tablename__ = 'test_scenario_results'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_identity: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='completed', nullable=False)
    detection_result: Mapped[str] = mapped_column(String(30), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False, default='{}')
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

