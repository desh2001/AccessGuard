from __future__ import annotations
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Local SQLite is ONLY used as a disposable automated test database.
os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
from database import get_session
from main import app
from models import Base, Account, AuditLog, AccessGrant, Review
from seed_demo import seed_demo


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / 'tests.db'
    engine = create_engine(f'sqlite+pysqlite:///{db_file}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        assert seed_demo(session) is True
        assert seed_demo(session) is False
    def override():
        with Session() as session:
            yield session
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c, Session
    app.dependency_overrides.clear()
    engine.dispose()


def test_inventory_and_account_mapping(client):
    c, Session = client
    overview = c.get('/api/overview').json()
    # 55 Human + 13 Machine + 6 Vendor = 74 identities
    assert overview['stats']['identities'] == 74
    # 5 unlinked orphan accounts in the new seed
    assert overview['stats']['unlinked_accounts'] == 5
    assert overview['stats']['linked_accounts'] > 0
    assert all('account_id' in r for r in c.get('/api/access').json())
    accounts = c.get('/api/accounts').json()
    assert len(accounts) == overview['stats']['accounts']
    suggestions = c.get('/api/accounts/suggestions').json()
    # First 2 of 5 unlinked have emails matching identity emails
    assert len(suggestions) == 2
    assert 'NOT verified' in suggestions[0]['reason']


def test_manual_verification_link_then_unlink_is_audited(client):
    c, Session = client
    first = next(a for a in c.get('/api/accounts').json() if a['mapping_status'] == 'Unlinked')
    id_ = first['id']
    bad = c.post(f'/api/accounts/{id_}/link', json={
        'identity_id': 'EMP-0001', 'reviewer': 'Research Supervisor',
        'verification_note': 'Confirmed in lab test records', 'confirmed': False})
    assert bad.status_code == 422
    body = {
        'identity_id': 'EMP-0001', 'reviewer': 'Research Supervisor',
        'verification_note': 'Verified ownership against synthetic lab directory records',
        'confirmed': True,
    }
    yes = c.post(f'/api/accounts/{id_}/link', json=body)
    assert yes.status_code == 200, yes.text
    assert yes.json()['mapping_status'] == 'Linked'
    assert c.post(f'/api/accounts/{id_}/link', json=body).status_code == 409
    assert c.get('/api/overview').json()['stats']['unlinked_accounts'] == 4
    events = c.get('/api/audit').json()
    assert any(e['action'] == 'ACCOUNT_LINKED' for e in events)
    no = c.post(f'/api/accounts/{id_}/unlink', json={
        'reviewer': 'Research Supervisor',
        'reason': 'Recheck identity mapping before audit', 'confirmed': True})
    assert no.status_code == 200
    assert c.get('/api/overview').json()['stats']['unlinked_accounts'] == 5
    assert any(e['action'] == 'ACCOUNT_UNLINKED' for e in c.get('/api/audit').json())


def test_reject_duplicate_external_accounts_and_invalid_identity(client):
    c, Session = client
    body = {'system_id': 'GH', 'external_account_id': 'lab-dupe', 'username': 'labuser'}
    assert c.post('/api/accounts', json=body).status_code == 201
    assert c.post('/api/accounts', json=body).status_code == 409
    assert c.post('/api/accounts', json={**body, 'system_id': 'NOT_REAL'}).status_code == 404
    new_id = next(a['id'] for a in c.get('/api/accounts').json() if a['external_account_id'] == 'lab-dupe')
    assert c.post(f'/api/accounts/{new_id}/link', json={
        'identity_id': 'INVALID', 'reviewer': 'Demo Tester',
        'verification_note': 'Verified from sample directory', 'confirmed': True,
    }).status_code == 404


def test_review_approval_then_demo_revoke(client):
    c, Session = client
    pending = next(r for r in c.get('/api/reviews').json() if r['review_status'] == 'Pending')
    rid = pending['review_id']
    assert c.post(f'/api/reviews/{rid}/simulate-revoke').status_code == 409
    assert c.post(f'/api/reviews/{rid}/decision', json={
        'decision': 'approve', 'reviewer': 'Demo Supervisor'}).status_code == 200
    assert c.post(f'/api/reviews/{rid}/simulate-revoke').status_code == 200
    with Session() as db:
        assert db.get(Review, rid).status == 'Remediated'
        assert db.get(AccessGrant, pending['grant_id']).status == 'Revoked'
    assert any(e['action'] == 'SIMULATED_REVOKE' for e in c.get('/api/audit').json())
    assert c.post(f'/api/reviews/{rid}/simulate-revoke').status_code == 409


def test_unknown_activity_not_inactivity(client):
    c, Session = client
    rows = c.get('/api/access').json()
    missing = next(x for x in rows if x['last_verified_use'] is None)
    assert any('NOT' in reason or 'not prove' in reason.lower() for reason in missing['reasons'])


def test_new_endpoints_available(client):
    c, _ = client
    assert c.get('/api/metrics').status_code == 200
    assert c.get('/api/stats/timeline').status_code == 200
    m = c.get('/api/metrics').json()
    assert 'avg_risk_score' in m
    assert 'admin_grants' in m
    assert m['total_active_grants'] > 0
    tl = c.get('/api/stats/timeline').json()
    assert len(tl) == 30
    assert all('date' in d for d in tl)
