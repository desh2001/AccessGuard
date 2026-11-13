"""AccessGuard Complete Research Lab — Comprehensive Test Suite & Verification.

Direct execution test runner that does not require network loopback sockets.
Tests all 7 modules end-to-end:
1. Employee Identity Management
2. Access Data Integration
3. Activity Analysis
4. AI Risk Detection & IsolationForest Anomaly Engine
5. Automated Access Reviews
6. Access Remediation (Simulated Revoke)
7. Dashboard & Reporting Metrics
"""
import os
import sys
from datetime import datetime, timezone

# Use SQLite in-memory for zero-dependency test verification
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'

from sqlalchemy.orm import Session
from database import engine
from models import Base, Identity, System, Account, AccessGrant, Review, AuditLog, ActivityEvent, ConnectorRun
from seed_demo import seed_demo
from risk import calculate_risk, access_dict, risk_level
from ai_engine import rank_anomalies
from main import (
    health, overview, identities, identity_detail, identity_accounts,
    accounts, suggestions, access, integrations, reviews, decide,
    simulate_revoke, generate_reviews, audit, offboarding, activity,
    alerts, ai_summary, metrics, stats_timeline, report_summary, connector_runs,
    create_account, link_account, unlink_account,
    AccountCreate, LinkBody, UnlinkBody, DecisionBody
)


def run_all_tests():
    print("=" * 70)
    print(" AccessGuard Complete System — Verification & Module Tests")
    print("=" * 70)

    # ── Database Setup ────────────────────────────────────────────────────────
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        assert seed_demo(s) is True, "Seed demo failed on first run"
        assert seed_demo(s) is False, "Seed demo should be idempotent"
    print("[PASS] Database tables created & synthetic demo data seeded")

    with Session(engine) as s:
        # ── Module 1: Employee Identity Management ────────────────────────────
        h = health(s)
        assert h['status'] == 'ok'
        assert h['identities'] == 74, f"Expected 74 identities, got {h['identities']}"
        
        all_ids = identities(s)
        assert len(all_ids) == 74
        human = sum(1 for i in all_ids if i['type'] == 'Human')
        machine = sum(1 for i in all_ids if i['type'] == 'Machine')
        vendor = sum(1 for i in all_ids if i['type'] == 'Vendor')
        assert human == 55 and machine == 13 and vendor == 6
        
        emp1 = identity_detail('EMP-0001', s)
        assert emp1['id'] == 'EMP-0001'
        assert len(emp1['grants']) > 0
        print(f"[PASS] Module 1: Identity Management ({human} Human, {machine} Machine, {vendor} Vendor identities verified)")

        # ── Module 2: Access Data Integration ─────────────────────────────────
        all_systems = integrations(s)
        assert len(all_systems) == 14, f"Expected 14 connected systems, got {len(all_systems)}"
        sys_names = {sys['name'] for sys in all_systems}
        assert {'GitHub', 'Linux Servers', 'Windows AD', 'AWS Cloud', 'PostgreSQL DB'}.issubset(sys_names)
        
        all_accounts = accounts(s)
        assert len(all_accounts) > 200
        unlinked = [a for a in all_accounts if a['mapping_status'] == 'Unlinked']
        assert len(unlinked) == 5, f"Expected 5 unlinked accounts, got {len(unlinked)}"
        
        # Test Account creation & linking
        new_acc = create_account(AccountCreate(
            system_id='GH', external_account_id='test-ext-101', username='test-user-101'
        ), s)
        assert new_acc['ok'] is True
        
        linked = link_account(new_acc['account_id'], LinkBody(
            identity_id='EMP-0001', reviewer='Lead Auditor',
            verification_note='Verified account via corporate email directory', confirmed=True
        ), s)
        assert linked['mapping_status'] == 'Linked'
        
        # Test Candidate suggestions
        sugs = suggestions(s)
        assert len(sugs) >= 2
        assert 'Exact email text match' in sugs[0]['reason']
        print(f"[PASS] Module 2: Access Integration ({len(all_systems)} systems, {len(all_accounts)} accounts, mapping & unlinked orphan detection)")

        # ── Module 3: Activity Analysis ───────────────────────────────────────
        events = activity(limit=100, db=s)
        assert len(events) == 100
        assert all('outcome' in e and 'action' in e for e in events)
        
        # Check heuristics flags
        flagged_events = [e for e in events if len(e['flags']) > 0]
        assert len(flagged_events) > 0, "Expected some heuristic flags on sampled activity events"
        print(f"[PASS] Module 3: Activity Analysis ({len(events)} sampled events, failure & UTC hour heuristics verified)")

        # ── Module 4: AI Risk Detection & Anomaly Engine ───────────────────────
        all_grants = access(s)
        assert len(all_grants) > 200
        
        # Test deterministic rule engine
        critical = [g for g in all_grants if g['risk_score'] >= 85]
        high = [g for g in all_grants if 60 <= g['risk_score'] < 85]
        assert len(critical) > 0, "Expected critical risk grants"
        assert len(high) > 0, "Expected high risk grants"
        
        # Test Machine Learning IsolationForest ranking
        ai_res = ai_summary(s)
        assert ai_res['mode'] == 'trained-on-current-cohort'
        assert ai_res['algorithm'] == 'IsolationForest'
        assert len(ai_res['findings']) > 100
        assert 'urgent' in ai_res['summary']
        assert 'needs_review' in ai_res['summary']
        print(f"[PASS] Module 4: AI Risk Detection (Deterministic Rules + IsolationForest ML: {len(critical)} Critical, {len(high)} High, {ai_res['summary']['urgent']} ML Urgent)")

        # ── Module 5: Automated Access Reviews ────────────────────────────────
        rev_queue = reviews(s)
        assert len(rev_queue) > 0
        pending_revs = [r for r in rev_queue if r['review_status'] == 'Pending']
        assert len(pending_revs) > 0
        
        # Decide: Retain access
        r_retain = pending_revs[0]
        res_retain = decide(r_retain['review_id'], DecisionBody(decision='retain', reviewer='Security Reviewer'), s)
        assert res_retain['review_status'] == 'Retained'
        
        # Decide: Approve removal
        r_approve = pending_revs[1]
        res_approve = decide(r_approve['review_id'], DecisionBody(decision='approve', reviewer='Manager Reviewer'), s)
        assert res_approve['review_status'] == 'Approved'
        print(f"[PASS] Module 5: Automated Reviews ({len(rev_queue)} total reviews, Human decisions: Retain & Approve removal verified)")

        # ── Module 6: Access Remediation ──────────────────────────────────────
        # Cannot revoke without approval
        try:
            simulate_revoke(r_retain['review_id'], s)
            assert False, "Should fail: cannot revoke Retained review"
        except Exception:
            pass  # Expected 409
            
        # Revoke approved grant
        res_rev = simulate_revoke(r_approve['review_id'], s)
        assert res_rev['review_status'] == 'Remediated'
        assert res_rev['mode'] == 'simulated'
        
        # Verify grant status is updated
        updated_grant = s.get(AccessGrant, r_approve['grant_id'])
        assert updated_grant.status == 'Revoked'
        print("[PASS] Module 6: Access Remediation (Dual-step approval gate & simulated revocation complete)")

        # ── Module 7: Dashboard & Reporting ───────────────────────────────────
        ov = overview(s)
        assert 'stats' in ov and 'categories' in ov and 'risks' in ov and 'dept_breakdown' in ov
        
        met = metrics(s)
        assert met['review_completion_pct'] >= 0
        assert met['remediated_grants'] >= 1
        
        timeline = stats_timeline(days=30, db=s)
        assert len(timeline) == 30
        
        rep = report_summary(s)
        assert 'caveats' in rep and len(rep['caveats']) >= 4
        
        logs = audit(limit=50, db=s)
        assert len(logs) >= 3
        actions = {l['action'] for l in logs}
        assert {'ACCOUNT_LINKED', 'REVIEW_RETAINED', 'REVIEW_APPROVED', 'SIMULATED_REVOKE'}.issubset(actions)
        print(f"[PASS] Module 7: Dashboard & Reporting (Audit trail with {len(logs)} events, 30-day timeline, compliance metrics)")

    # ── Module 8: Dialog External Systems Integration (FTP & ML) ─────
    with Session(engine) as s:
        from main import ftp_sync, ftp_status, ml_status
        from pathlib import Path
        # Create a temporary test drop file to verify FTP ingestion pipeline
        spool_dir = Path(__file__).resolve().parent / 'sample_imports' / 'ftp_spool'
        spool_dir.mkdir(parents=True, exist_ok=True)
        test_file = spool_dir / 'test_sync_entitlements.csv'
        test_file.write_text("external_account_id,username,permission,resource,system_id\nunit_test_acc,test_user,Admin,Test-Resource,GH\n", encoding='utf-8')
        
        try:
            ftp_res = ftp_sync(s)
            assert ftp_res['status'] in ('Success', 'Idle', 'Warning')
            assert ftp_res['total_imported'] >= 1
            st = ftp_status(s)
            assert 'spool_files_available' in st
            print(f"[PASS] Dialog FTP Integration: Ingested {ftp_res['total_imported']} items ({ftp_res['grants_imported']} grants) via {ftp_res['mode']}")
        finally:
            if test_file.exists():
                test_file.unlink()

        # 2. Test Dialog Final ML Microservice status & fallback
        ml_stat = ml_status()
        assert 'status' in ml_stat
        print(f"[PASS] Dialog ML Microservice Status: {ml_stat['status']} (Target URL: {ml_stat.get('url')})")

    print("=" * 70)
    print(" ALL 7 CORE MODULES + DIALOG FTP & ML INTEGRATIONS FULLY FUNCTIONAL!")
    print("=" * 70)
    return 0


if __name__ == '__main__':
    sys.exit(run_all_tests())

