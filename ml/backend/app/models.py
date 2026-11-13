from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, Float, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(30), default="reviewer")

class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(180), unique=True)
    department: Mapped[str] = mapped_column(String(80))
    job_title: Mapped[str] = mapped_column(String(100))
    manager_username: Mapped[str] = mapped_column(String(100), default="reviewer")
    status: Mapped[str] = mapped_column(String(30), default="active")
    accounts: Mapped[list["Account"]] = relationship(back_populates="employee")

class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform", "username", name="uq_platform_username"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    platform: Mapped[str] = mapped_column(String(60), index=True)
    username: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="active")
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    employee: Mapped[Employee | None] = relationship(back_populates="accounts")
    entitlements: Mapped[list["Entitlement"]] = relationship(back_populates="account")

class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (UniqueConstraint("account_id", "resource", "permission", name="uq_entitlement"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    resource: Mapped[str] = mapped_column(String(180))
    permission: Mapped[str] = mapped_column(String(60))
    sensitivity: Mapped[str] = mapped_column(String(30), default="medium")
    source: Mapped[str] = mapped_column(String(80), default="csv")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    account: Mapped[Account] = relationship(back_populates="entitlements")

class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_occurred_account", "occurred_at", "account_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    resource: Mapped[str] = mapped_column(String(180))
    event_type: Mapped[str] = mapped_column(String(60))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(80))

class ActivityCoverage(Base):
    """Administrator-attested ingestion coverage, NOT evidence that access is necessary."""
    __tablename__ = "activity_coverage"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(60), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(80))
    attested_by: Mapped[str] = mapped_column(String(120))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class DirectorySnapshot(Base):
    """Source-provided AD reporting and data-coverage snapshot; NOT an HR certification."""
    __tablename__ = "directory_snapshots"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime)
    reporting_manager: Mapped[str | None] = mapped_column(String(160), nullable=True)
    org_unit: Mapped[str | None] = mapped_column(String(180), nullable=True)
    ad_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    groups_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_history_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(80))

class ADGroupMembership(Base):
    """Explicit current AD group assignments. 'privileged' requires known governance mapping."""
    __tablename__ = "ad_group_memberships"
    __table_args__ = (UniqueConstraint("employee_id", "organization_key", "directory_key", "group_key", name="uq_employee_ad_group_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    group_name: Mapped[str] = mapped_column(String(200))
    # Stable directory group identity, scoped per organization and directory.
    # Legacy exports without SID/GUID use a directory-qualified name fallback.
    organization_key: Mapped[str] = mapped_column(String(100), default="demo")
    directory_key: Mapped[str] = mapped_column(String(120), default="primary")
    group_key: Mapped[str] = mapped_column(String(220), default="unknown")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    privileged: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(80))
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ADGroupMembershipHistory(Base):
    """Append-only observed group memberships for accurate as-of account features."""
    __tablename__ = 'ad_group_membership_history'
    __table_args__ = (UniqueConstraint('employee_id', 'organization_key', 'directory_key',
                                       'group_key', 'observed_at', name='uq_ad_membership_observation'),
                      Index('ix_ad_history_asof', 'employee_id', 'observed_at'))
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'), index=True)
    organization_key: Mapped[str] = mapped_column(String(100))
    directory_key: Mapped[str] = mapped_column(String(120))
    group_key: Mapped[str] = mapped_column(String(220))
    display_name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(80))

class ADGroupCatalog(Base):
    """Organization-owned group meaning; raw names alone are not permission evidence."""
    __tablename__ = "ad_group_catalog"
    __table_args__ = (UniqueConstraint("organization_key", "directory_key", "group_key", name="uq_ad_catalog_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_key: Mapped[str] = mapped_column(String(100), default="demo", index=True)
    directory_key: Mapped[str] = mapped_column(String(120), default="primary")
    group_key: Mapped[str] = mapped_column(String(220))
    display_name: Mapped[str] = mapped_column(String(200))
    group_kind: Mapped[str] = mapped_column(String(30), default="unknown")
    access_relevance: Mapped[str] = mapped_column(String(30), default="unknown")
    privilege_tier: Mapped[str] = mapped_column(String(30), default="unknown")
    risk_tier: Mapped[str] = mapped_column(String(30), default="unknown")
    resource_scope: Mapped[str | None] = mapped_column(String(300), nullable=True)
    allowed_departments: Mapped[list] = mapped_column(JSON, default=list)
    approved_by: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(120))
    policy_version: Mapped[str] = mapped_column(String(40), default="v1")
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class TransferAccessDisposition(Base):
    """Per-transfer, per-account recertification; transfer stays pending until reviewed."""
    __tablename__ = "transfer_access_dispositions"
    __table_args__ = (UniqueConstraint("transfer_id", "account_id", name="uq_transfer_account_disposition"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("employee_transfers.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("periodic_review_cycles.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(30))
    reviewed_by: Mapped[str] = mapped_column(String(100))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    rationale: Mapped[str] = mapped_column(Text)

class EmployeeTransfer(Base):
    """Recorded changes in employee scope. Each event must be sourced and dated."""
    __tablename__ = "employee_transfers"
    __table_args__ = (UniqueConstraint("employee_id", "occurred_at", "source", name="uq_transfer_event"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    from_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    from_manager: Mapped[str | None] = mapped_column(String(160), nullable=True)
    to_manager: Mapped[str | None] = mapped_column(String(160), nullable=True)
    from_org_unit: Mapped[str | None] = mapped_column(String(180), nullable=True)
    to_org_unit: Mapped[str | None] = mapped_column(String(180), nullable=True)
    source: Mapped[str] = mapped_column(String(80))

class ADGroupChange(Base):
    __tablename__ = "ad_group_changes"
    __table_args__ = (UniqueConstraint("employee_id", "group_name", "occurred_at", "action", name="uq_ad_group_change"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    group_name: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(12))  # added / removed
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(80))



class GovernedResourcePolicy(Base):
    """Approved policy for an enterprise-managed resource, NOT arbitrary browsing.

    Company-approved mappings only. A blank allowed list asserts NO access
    restriction; it must not be interpreted as a deny-all list. Policies are
    source-scoped and effective-dated, and are only advisory review evidence.
    """
    __tablename__ = 'governed_resource_policies'
    __table_args__ = (UniqueConstraint('organization_key','platform','resource_kind','resource_key',
                                      'policy_version', name='uq_governed_resource_version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_key: Mapped[str] = mapped_column(String(100), default='demo', index=True)
    platform: Mapped[str] = mapped_column(String(60))
    resource_kind: Mapped[str] = mapped_column(String(40))
    resource_key: Mapped[str] = mapped_column(String(180))
    # Explicit organization-approved access allowlists; no inference from a name.
    allowed_departments: Mapped[list] = mapped_column(JSON, default=list)
    allowed_job_titles: Mapped[list] = mapped_column(JSON, default=list)
    approved_by: Mapped[str] = mapped_column(String(120))
    policy_version: Mapped[str] = mapped_column(String(40))
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class GovernedResourceUse(Base):
    """Verified company-managed resource usage, never general browser history.

    Source agents must only send allowlisted business applications or managed
    software assets. Collection of personal URLs, music, search terms or page
    contents is out of scope. A process execution event alone does not prove
    entitlement authorization; results only trigger a human policy review.
    """
    __tablename__ = 'governed_resource_uses'
    __table_args__ = (UniqueConstraint('event_key', name='uq_governed_usage_event_key'),
                      Index('ix_governed_uses_account_time', 'account_id', 'occurred_at'))
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(150))
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    resource_kind: Mapped[str] = mapped_column(String(40))
    resource_key: Mapped[str] = mapped_column(String(180))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(100))
    # Verified event from managed collector, not a user-typed claim.
    source_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(20), default='observed')

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    entitlement_id: Mapped[int] = mapped_column(ForeignKey("entitlements.id"))
    assigned_to: Mapped[str] = mapped_column(String(100), default="reviewer")
    state: Mapped[str] = mapped_column(String(30), default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remediation_state: Mapped[str] = mapped_column(String(30), default="not_requested")
    remediation_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entitlement: Mapped[Entitlement] = relationship()

class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class PeriodicReviewCycle(Base):
    """One frozen, dated human certification campaign (snapshot of selected accounts)."""
    __tablename__ = "periodic_review_cycles"
    id: Mapped[int] = mapped_column(primary_key=True)
    review_window_days: Mapped[int] = mapped_column(Integer)
    review_budget_percent: Mapped[float] = mapped_column(Float)
    window_end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(100))
    total_accounts: Mapped[int] = mapped_column(Integer)
    selected_accounts: Mapped[int] = mapped_column(Integer)
    mandatory_accounts: Mapped[int] = mapped_column(Integer)
    model_used: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="open")
    tasks: Mapped[list["PeriodicAccountReview"]] = relationship(back_populates="cycle")


class PeriodicAccountReview(Base):
    """One access certification task PER ACCOUNT, not one per log event/entitlement.

    Decisions are human-only; approving revocation never alters upstream permissions.
    """
    __tablename__ = "periodic_account_reviews"
    __table_args__ = (UniqueConstraint("cycle_id", "account_id", name="uq_periodic_account_cycle"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("periodic_review_cycles.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    assigned_to: Mapped[str] = mapped_column(String(100))
    priority: Mapped[str] = mapped_column(String(30))
    policy_score: Mapped[int] = mapped_column(Integer)
    anomaly_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(30), default="pending")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remediation_state: Mapped[str] = mapped_column(String(30), default="not_requested")
    cycle: Mapped[PeriodicReviewCycle] = relationship(back_populates="tasks")
    account: Mapped[Account] = relationship()
