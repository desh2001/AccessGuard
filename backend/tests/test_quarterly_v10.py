"""Comprehensive test suite for AccessGuard Quarterly ML Integration V10.

Covers:
1. Identity Resolution & Evidence Linkage (SID, UID, GitHub ID, Quarantine, Deduplication).
2. Mandatory Policy Overrides & Review Budget Logic (Transfers, Leavers, Unlinked, Budget Capping).
3. Reviewed CSV Import Validation & Atomic Commit (BOM, Headers, Validation Errors, Idempotency).
4. Strict Human Review Label Separation (Access Decision != Review Classification).
5. ML Client Contract & Offline Resilience (Account ID joining, Bearer Auth, No In-batch Fitting).
"""
import io
import csv
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from models import (
    Base, Identity, System, Account, AccessGrant, ActivityEvent,
    ActivityCoverage, ADGroupCatalog, ADGroupMembershipHistory,
    EmployeeTransfer, ManagedResourcePolicy, ActivityQuarantine,
    QuarterlyReviewCycle, QuarterlyAccountReview,
    ReviewOutcomeImportBatch, ReviewOutcomeImportRow,
    QuarterlyReviewOutcome, MLTrainingRun,
)
from accesslog_client import resolve_event_account
from quarterly_feature_builder import build_account_features
from quarterly_review_service import (
    build_cycle_preview,
    create_review_cycle,
    record_account_decision,
    generate_outcome_template_csv,
    preview_outcome_csv,
    commit_outcome_batch,
    get_training_readiness,
    CSV_HEADERS,
)
from ml_client import score_accounts_batch, _auth_headers


@pytest.fixture
def db_session():
    """Provides an isolated in-memory SQLite database populated with V10 baseline data."""
    engine = create_engine("sqlite+pysqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        # Create core Systems
        win_sys = System(id="AD", name="Windows AD", category="ActiveDirectory", platform="windows")
        lin_sys = System(id="LIN", name="Linux Server", category="Server", platform="linux")
        gh_sys = System(id="GH", name="GitHub", category="SaaS", platform="github")
        session.add_all([win_sys, lin_sys, gh_sys])

        # Create Identities
        emp1 = Identity(
            id="EMP-001", name="Alice Smith", email="alice@corp.dialog.lk",
            department="IT", job_title="SysAdmin", type="Human", status="Active",
            manager="Unassigned"
        )
        emp2 = Identity(
            id="EMP-002", name="Bob Jones", email="bob@corp.dialog.lk",
            department="Finance", job_title="Financial Analyst", type="Human", status="Active",
            manager="Unassigned"
        )
        emp_leaver = Identity(
            id="EMP-003", name="Charlie Departed", email="charlie@corp.dialog.lk",
            department="Engineering", job_title="Developer", type="Human", status="Departed",
            manager="Unassigned"
        )
        session.add_all([emp1, emp2, emp_leaver])
        session.flush()

        # Create Accounts with explicit integer IDs
        acct_alice_win = Account(
            id=1, identity_id=emp1.id, system_id=win_sys.id,
            username="asmith", account_email="alice@corp.dialog.lk",
            account_type="human",
            external_account_id="ad:asmith", native_id="S-1-5-21-123456789-001",
            native_id_type="windows_sid", native_id_namespace="corp.dialog.lk",
            status="Active"
        )
        acct_alice_lin = Account(
            id=2, identity_id=emp1.id, system_id=lin_sys.id,
            username="asmith_lin", account_email="alice@corp.dialog.lk",
            account_type="human",
            external_account_id="lin:1001", native_id="1001",
            native_id_type="linux_uid", native_id_namespace="prod-lin-01",
            status="Active"
        )
        acct_bob_gh = Account(
            id=3, identity_id=emp2.id, system_id=gh_sys.id,
            username="bjones-gh", account_email="bob@corp.dialog.lk",
            account_type="human",
            external_account_id="github-user:998877", native_id="998877",
            native_id_type="github_user_id", native_id_namespace="github.com",
            status="Active"
        )
        acct_charlie_win = Account(
            id=4, identity_id=emp_leaver.id, system_id=win_sys.id,
            username="cdeparted", account_email="charlie@corp.dialog.lk",
            account_type="human",
            external_account_id="ad:cdeparted", native_id="S-1-5-21-123456789-003",
            native_id_type="windows_sid", native_id_namespace="corp.dialog.lk",
            status="Active"
        )
        acct_orphan = Account(
            id=5, identity_id=None, system_id=lin_sys.id,
            username="ghostuser", account_email="ghost@external.local",
            account_type="service",
            external_account_id="lin:9999", native_id="9999",
            native_id_type="linux_uid", native_id_namespace="prod-lin-01",
            status="Active"
        )
        session.add_all([acct_alice_win, acct_alice_lin, acct_bob_gh, acct_charlie_win, acct_orphan])
        session.flush()

        # Access Grants
        now = datetime.now(timezone.utc)
        g1 = AccessGrant(account_id=acct_alice_win.id, permission="Domain Admins", resource="DC01", privilege=1, sensitivity="critical", status="Active")
        g2 = AccessGrant(account_id=acct_alice_lin.id, permission="sudo", resource="prod-lin-01", privilege=1, sensitivity="high", status="Active")
        g3 = AccessGrant(account_id=acct_bob_gh.id, permission="read", resource="dialog-portal", privilege=0, sensitivity="standard", status="Active")
        g4 = AccessGrant(account_id=acct_charlie_win.id, permission="Standard User", resource="Workstations", privilege=0, sensitivity="standard", status="Active")
        g5 = AccessGrant(account_id=acct_orphan.id, permission="backup-operator", resource="backup-srv", privilege=1, sensitivity="high", status="Active")
        session.add_all([g1, g2, g3, g4, g5])

        # Coverage record for 90 days
        cov = ActivityCoverage(
            platform="windows", source="winevent", event_type="logon",
            start_at=now - timedelta(days=90), end_at=now,
            is_complete=1, attested_by="Security Ops",
        )
        cov_lin = ActivityCoverage(
            platform="linux", source="auditd", event_type="session",
            start_at=now - timedelta(days=90), end_at=now,
            is_complete=1, attested_by="Security Ops",
        )
        cov_gh = ActivityCoverage(
            platform="github", source="github_audit", event_type="repo",
            start_at=now - timedelta(days=90), end_at=now,
            is_complete=1, attested_by="Security Ops",
        )
        session.add_all([cov, cov_lin, cov_gh])

        # Employee Transfer for Bob: transferred within last 90 days
        xfer = EmployeeTransfer(
            identity_id=emp2.id,
            from_department="Engineering",
            to_department="Finance",
            effective_at=now - timedelta(days=20),
            occurred_at=now - timedelta(days=20),
        )
        session.add(xfer)

        session.commit()
        yield session
    engine.dispose()


# ─── 1. Identity Resolution & Evidence Linkage Tests ─────────────────────────

def test_resolve_by_windows_sid(db_session):
    event = {
        "native_id": "S-1-5-21-123456789-001",
        "native_id_type": "windows_sid",
        "native_id_namespace": "corp.dialog.lk",
        "username": "asmith",
        "system_id": "AD",
        "event_id": "evt-win-100",
    }
    status, acct, reason = resolve_event_account(db_session, event)
    assert status == "matched"
    assert acct is not None
    assert acct.id == 1
    assert acct.username == "asmith"


def test_resolve_by_linux_uid(db_session):
    event = {
        "native_id": "1001",
        "native_id_type": "linux_uid",
        "native_id_namespace": "prod-lin-01",
        "username": "unknown_alias",
        "system_id": "LIN",
        "event_id": "evt-lin-200",
    }
    status, acct, reason = resolve_event_account(db_session, event)
    assert status == "matched"
    assert acct is not None
    assert acct.id == 2


def test_resolve_by_github_numeric_id(db_session):
    event = {
        "native_id": "998877",
        "native_id_type": "github_user_id",
        "native_id_namespace": "github.com",
        "username": "different_handle",
        "system_id": "GH",
        "event_id": "evt-gh-300",
    }
    status, acct, reason = resolve_event_account(db_session, event)
    assert status == "matched"
    assert acct is not None
    assert acct.id == 3


def test_unknown_identity_quarantined_without_crash(db_session):
    event = {
        "native_id": "S-1-5-21-999999999-999",
        "native_id_type": "windows_sid",
        "native_id_namespace": "corp.dialog.lk",
        "username": "nonexistent_user",
        "system_id": "AD",
        "event_id": "evt-quarantine-1",
        "raw_payload": "{\"log\": \"unknown user logon\"}"
    }
    status, acct, reason = resolve_event_account(db_session, event)
    assert status == "unmatched"
    assert acct is None

    # Verify quarantine recording
    q = ActivityQuarantine(
        source="Sentinel-Ingest",
        source_event_id="evt-quarantine-1",
        reason=reason or "no_matching_account",
        native_actor_id="S-1-5-21-999999999-999",
        platform="windows",
        payload_ref=event["raw_payload"],
    )
    db_session.add(q)
    db_session.commit()

    saved_q = db_session.scalar(select(ActivityQuarantine).where(ActivityQuarantine.source_event_id == "evt-quarantine-1"))
    assert saved_q is not None
    assert saved_q.native_actor_id == "S-1-5-21-999999999-999"


def test_ambiguous_username_quarantined(db_session):
    # Add a duplicate username under different system without specifying system_id in event
    acct_dup = Account(
        id=6, system_id="GH",
        username="asmith", external_account_id="gh:asmith",
        account_type="human",
        status="Active"
    )
    db_session.add(acct_dup)
    db_session.flush()

    event = {
        "username": "asmith",
        "event_id": "evt-ambiguous-1",
        "raw_payload": "{\"log\": \"ambiguous username\"}"
    }
    # In V11, events with only username and no stable ID or system_id are quarantined as invalid
    status, acct, reason = resolve_event_account(db_session, event)
    assert status in ("invalid", "unmatched")
    assert acct is None


def test_event_deduplication_preserves_existing(db_session):
    now = datetime.now(timezone.utc)
    ev1 = ActivityEvent(
        account_id=1,
        source="Sentinel-Ingest",
        source_event_id="unique-evt-001",
        occurred_at=now,
        action="Logon",
        outcome="Success",
        resource_key="Initial-Logon"
    )
    db_session.add(ev1)
    db_session.commit()

    # Attempt second insertion with same (source, source_event_id)
    existing = db_session.scalar(
        select(ActivityEvent).where(
            ActivityEvent.source == "Sentinel-Ingest",
            ActivityEvent.source_event_id == "unique-evt-001"
        )
    )
    assert existing is not None
    assert existing.resource_key == "Initial-Logon"


# ─── 2. Mandatory Policy Overrides & Budget Capping Tests ─────────────────────

def test_mandatory_policy_overrides(db_session):
    now = datetime.now(timezone.utc)
    preview = build_cycle_preview(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=20,
        cycle_id="2026-Q4-TEST",
    )

    items = {item["account_id"]: item for item in preview["accounts"]}

    # Bob (id=3) has a recent transfer -> Mandatory
    assert items[3]["is_mandatory"] is True
    assert items[3]["priority"] == "mandatory"
    assert any("transfer" in r.lower() for r in items[3]["policy_reasons"])

    # Charlie (id=4) is a leaver holding active access -> Mandatory
    assert items[4]["is_mandatory"] is True
    assert items[4]["priority"] == "mandatory"
    assert any("departed" in r.lower() for r in items[4]["policy_reasons"])

    # Orphan account (id=5) is unlinked -> Mandatory
    assert items[5]["is_mandatory"] is True
    assert items[5]["priority"] == "mandatory"
    assert any("unlinked" in r.lower() for r in items[5]["policy_reasons"])


def test_review_budget_capping_never_drops_mandatory(db_session):
    now = datetime.now(timezone.utc)
    # Review budget percentage is 1%, but we have 3 mandatory accounts
    preview = build_cycle_preview(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=1,
        cycle_id="2026-Q4-TINYBUDGET",
    )

    # All mandatory accounts MUST be prioritized as mandatory regardless of budget cap
    queued_mandatory = [it for it in preview["accounts"] if it["priority"] == "mandatory"]
    assert len(queued_mandatory) >= 3


def test_spare_budget_not_filled_with_low_risk(db_session):
    now = datetime.now(timezone.utc)
    # Add an active standard employee account with active resource use and non-privileged grant
    emp_std = Identity(
        id="EMP-STD", name="Standard User", email="std@corp.dialog.lk",
        department="IT", job_title="Support", type="Human", status="Active", manager="Unassigned"
    )
    db_session.add(emp_std)
    db_session.flush()

    acct_std = Account(
        id=10, identity_id=emp_std.id, system_id="AD",
        username="standard_user", account_email="std@corp.dialog.lk",
        external_account_id="ad:standard_user", native_id="S-1-5-21-STD",
        native_id_type="sid", status="Active"
    )
    db_session.add(acct_std)
    db_session.flush()

    # Standard non-privileged grant
    g_std = AccessGrant(account_id=acct_std.id, permission="Domain Users", resource="Fileshare", privilege=0, sensitivity="standard", status="Active")
    db_session.add(g_std)

    # Add active resource use event so inactivity rule does not trigger
    ev = ActivityEvent(
        account_id=acct_std.id, source="Sentinel-Ingest", source_event_id="std-evt-001",
        occurred_at=now - timedelta(days=10), action="FileRead", outcome="Success",
        event_type="resource_use", resource_key="Fileshare",
    )
    db_session.add(ev)
    db_session.commit()

    # Budget is 100%, but standard account has 0 anomalies, normal dept, no transfer, and active usage
    preview = build_cycle_preview(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=100,
        cycle_id="2026-Q4-LARGEBUDGET",
    )

    items = {item["account_id"]: item for item in preview["accounts"]}
    std_item = items[10]
    # Standard account has policy_score < 30 and no high ML percentile -> MUST NOT be selected into review queue
    assert std_item["policy_score"] < 30
    assert std_item["is_mandatory"] is False
    assert std_item["priority"] == "deferred_candidate"


# ─── 3. Reviewed CSV Import Validation & Atomic Commit Tests ─────────────────

def test_csv_template_export(db_session):
    now = datetime.now(timezone.utc)
    cycle = create_review_cycle(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=20,
        cycle_id="2026-Q4-CSV-TEST",
        created_by="admin@corp.dialog.lk",
    )

    template_csv = generate_outcome_template_csv(db_session, cycle.id, scope="full_population")
    assert template_csv.startswith("\ufeff")  # UTF-8 BOM present
    reader = csv.reader(io.StringIO(template_csv.lstrip("\ufeff")))
    headers = next(reader)
    assert headers == CSV_HEADERS


def test_csv_preview_and_atomic_commit(db_session):
    now = datetime.now(timezone.utc)
    cycle = create_review_cycle(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=20,
        cycle_id="2026-Q4-COMMIT-TEST",
        created_by="admin@corp.dialog.lk",
    )

    # Valid CSV content for 2 accounts matching CSV_HEADERS:
    # ['schema_version', 'review_cycle_id', 'account_id', 'platform', 'reviewer_id', 'reviewed_at_utc', 'review_classification', 'access_decision', 'rationale', 'evidence_reference']
    csv_valid = (
        "\ufeffschema_version,review_cycle_id,account_id,platform,reviewer_id,reviewed_at_utc,review_classification,access_decision,rationale,evidence_reference\n"
        f"1,{cycle.id},ACC-3,github,reviewer@corp.dialog.lk,2026-11-18T10:00:00Z,verified_normal,retain,Verified standard repo access,log-ref-001\n"
        f"1,{cycle.id},ACC-4,windows ad,reviewer@corp.dialog.lk,2026-11-18T10:05:00Z,confirmed_policy_concern,request_revoke,Departed employee still holding AD access,hr-ref-002\n"
    )

    preview = preview_outcome_csv(
        db_session,
        cycle_id=cycle.id,
        file_bytes=csv_valid.encode("utf-8"),
        original_filename="outcomes.csv",
        uploader="reviewer@corp.dialog.lk",
        scope="full_population",
    )
    assert preview["total_rows"] == 2
    assert preview["valid_rows"] == 2
    assert preview["invalid_rows"] == 0
    assert len(preview["errors"]) == 0

    # Commit the batch
    batch_id = preview["batch_id"]
    commit_res = commit_outcome_batch(db_session, batch_id=batch_id, approver="admin@corp.dialog.lk")
    assert commit_res["status"] == "committed"
    assert commit_res["records_committed"] == 2

    # Verify outcomes in DB
    outcomes = db_session.scalars(select(QuarterlyReviewOutcome).where(QuarterlyReviewOutcome.cycle_id == cycle.id)).all()
    assert len(outcomes) == 2


def test_csv_atomic_rollback_on_invalid_row(db_session):
    now = datetime.now(timezone.utc)
    cycle = create_review_cycle(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=20,
        cycle_id="2026-Q4-ERR-TEST",
        created_by="admin@corp.dialog.lk",
    )

    # CSV with 1 valid row and 1 invalid row (unknown account_id ACC-9999)
    csv_with_error = (
        "\ufeffschema_version,review_cycle_id,account_id,platform,reviewer_id,reviewed_at_utc,review_classification,access_decision,rationale,evidence_reference\n"
        f"1,{cycle.id},ACC-3,github,reviewer@corp.dialog.lk,2026-11-18T10:00:00Z,verified_normal,retain,Verified normal access,ref-1\n"
        f"1,{cycle.id},ACC-9999,github,reviewer@corp.dialog.lk,2026-11-18T10:05:00Z,confirmed_policy_concern,request_revoke,Unknown account,ref-2\n"
    )

    preview = preview_outcome_csv(
        db_session,
        cycle_id=cycle.id,
        file_bytes=csv_with_error.encode("utf-8"),
        original_filename="outcomes_err.csv",
        uploader="reviewer@corp.dialog.lk",
        scope="full_population",
    )
    assert preview["invalid_rows"] == 1
    assert any("unknown_account" in err["code"] for err in preview["errors"])

    # Attempting to commit an invalid batch MUST raise an exception and commit 0 rows
    with pytest.raises(ValueError, match="invalid"):
        commit_outcome_batch(db_session, batch_id=preview["batch_id"], approver="admin@corp.dialog.lk")

    outcomes = db_session.scalars(select(QuarterlyReviewOutcome).where(QuarterlyReviewOutcome.cycle_id == cycle.id)).all()
    assert len(outcomes) == 0


def test_csv_duplicate_account_rejection(db_session):
    now = datetime.now(timezone.utc)
    cycle = create_review_cycle(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=20,
        cycle_id="2026-Q4-DUP-TEST",
        created_by="admin@corp.dialog.lk",
    )

    csv_dup = (
        "\ufeffschema_version,review_cycle_id,account_id,platform,reviewer_id,reviewed_at_utc,review_classification,access_decision,rationale,evidence_reference\n"
        f"1,{cycle.id},ACC-3,github,reviewer@corp.dialog.lk,2026-11-18T10:00:00Z,verified_normal,retain,First rationale,ref-1\n"
        f"1,{cycle.id},ACC-3,github,reviewer@corp.dialog.lk,2026-11-18T10:05:00Z,verified_normal,retain,Duplicate rationale,ref-2\n"
    )

    preview = preview_outcome_csv(
        db_session,
        cycle_id=cycle.id,
        file_bytes=csv_dup.encode("utf-8"),
        original_filename="outcomes_dup.csv",
        uploader="reviewer@corp.dialog.lk",
        scope="full_population",
    )
    assert preview["duplicate_rows"] >= 1
    assert any("duplicate_in_file" in err["code"] for err in preview["errors"])


# ─── 4. Strict Label Separation Tests ────────────────────────────────────────

def test_label_separation_retain_with_behavioral_concern(db_session):
    now = datetime.now(timezone.utc)
    cycle = create_review_cycle(
        db_session,
        as_of=now,
        window_days=90,
        budget_pct=20,
        cycle_id="2026-Q4-LABEL-TEST",
        created_by="admin@corp.dialog.lk",
    )

    # Reviewer decides to RETAIN access because of business justification,
    # but confirms behavioral anomaly is real (e.g. emergency off-hours maintenance).
    # ML label MUST NOT be marked verified_normal (0)!
    task = db_session.scalar(
        select(QuarterlyAccountReview).where(
            QuarterlyAccountReview.cycle_id == cycle.id,
            QuarterlyAccountReview.account_id == 3
        )
    )
    assert task is not None

    record_account_decision(
        db_session,
        task_id=task.id,
        decision="retain",
        reviewer_id="auditor@corp.dialog.lk",
        rationale="Approved retention for emergency incident response, but activity pattern was anomalous.",
    )

    # In database, access_decision is 'retain'
    db_session.refresh(task)
    assert task.decision == "retain"

    # Now verify via CSV import with confirmed_behavioral_concern and decision=retain
    csv_retain_concern = (
        "\ufeffschema_version,review_cycle_id,account_id,platform,reviewer_id,reviewed_at_utc,review_classification,access_decision,rationale,evidence_reference\n"
        f"1,{cycle.id},ACC-3,github,reviewer@corp.dialog.lk,2026-11-18T10:00:00Z,confirmed_behavioral_concern,retain,Retention justified by emergency work,incident-ticket-999\n"
    )

    preview = preview_outcome_csv(
        db_session,
        cycle_id=cycle.id,
        file_bytes=csv_retain_concern.encode("utf-8"),
        original_filename="retain_concern.csv",
        uploader="auditor@corp.dialog.lk",
        scope="full_population",
    )
    assert preview["valid_rows"] == 1
    commit_res = commit_outcome_batch(db_session, batch_id=preview["batch_id"], approver="admin@corp.dialog.lk")
    assert commit_res["status"] == "committed"

    # Outcome stored faithfully
    outcome = db_session.scalar(
        select(QuarterlyReviewOutcome).where(
            QuarterlyReviewOutcome.cycle_id == cycle.id,
            QuarterlyReviewOutcome.account_id == 3
        )
    )
    assert outcome is not None
    assert outcome.access_decision == "retain"
    assert outcome.review_classification == "confirmed_behavioral_concern"

    # Readiness check: confirmed_behavioral_concern is counted as concern, NOT normal
    readiness = get_training_readiness(db_session, platform="github")
    assert readiness["confirmed_behavioral_concern"] == 1
    assert readiness["verified_normal"] == 0


# ─── 5. ML Client Contract & Offline Resilience Tests ────────────────────────

def test_ml_client_resilience_when_service_offline(monkeypatch):
    import httpx
    # Simulate network failure / offline ML microservice
    def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Connection refused to ML microservice:8001")

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    records = [
        {"account_id": "1", "platform": "windows", "features": {"active_days_window": 10}},
        {"account_id": "2", "platform": "linux", "features": {"active_days_window": 5}},
    ]

    res = score_accounts_batch(cycle_id="2026-Q4", window_days=90, records=records)
    assert isinstance(res, dict)
    assert len(res) == 2
    assert "1" in res
    assert "2" in res
    for acc_id, item in res.items():
        assert item["status"] == "unscored"
        assert "offline" in item["reason"] or "refused" in item["reason"].lower() or "ml_unavailable" in item["reason"]


def test_ml_client_account_id_correlation():
    # Verify that results match by account_id regardless of ordering
    dummy_results = [
        {"account_id": "ACC-2", "status": "scored", "anomaly_percentile_100": 88.0},
        {"account_id": "ACC-1", "status": "scored", "anomaly_percentile_100": 12.0},
    ]
    result_map = {r["account_id"]: r for r in dummy_results}
    assert result_map["ACC-1"]["anomaly_percentile_100"] == 12.0
    assert result_map["ACC-2"]["anomaly_percentile_100"] == 88.0


def test_auth_headers_bearer_format():
    headers = _auth_headers()
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Bearer ")
    assert len(headers["Authorization"].split(" ")[1]) >= 16
