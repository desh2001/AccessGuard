"""Phase 2 canonical identity and technical-account schema."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


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
    account: Mapped[Account] = relationship(back_populates='grants')
    __table_args__ = (CheckConstraint("status IN ('Active','Revoked')", name='grant_status_valid'),)


class Review(Base):
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
    """Synthetic or imported activity evidence; absence of events is NOT proof of unused access."""
    __tablename__ = 'activity_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'), index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(70), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default='DemoSeed')
    __table_args__ = (CheckConstraint("outcome IN ('Success','Failure')", name='activity_outcome_valid'),)


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
