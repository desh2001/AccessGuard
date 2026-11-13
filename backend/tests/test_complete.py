"""Extended modules are tested with disposable SQLite; no credentials or external writes."""
from __future__ import annotations
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import httpx

os.environ.setdefault('DATABASE_URL','sqlite+pysqlite:///:memory:')
from models import Base, Account, AuditLog, AccessGrant, ActivityEvent, ConnectorRun
from database import get_session
from seed_demo import seed_demo
from main import app
from ai_engine import rank_anomalies
from connectors.csv_import import import_csv
from connectors.github_readonly import sync


@pytest.fixture
def setup(tmp_path):
    engine=create_engine(f'sqlite+pysqlite:///{tmp_path / "complete.db"}')
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine,expire_on_commit=False)
    with Session() as db:
        assert seed_demo(db)
    def override():
        with Session() as db:yield db
    app.dependency_overrides[get_session]=override
    with TestClient(app) as client:yield client,Session
    app.dependency_overrides.clear()
    engine.dispose()


def test_extended_endpoints(setup):
    client,_=setup
    assert client.get('/api/health').json()['status']=='ok'
    assert client.get('/api/activity').status_code==200
    assert len(client.get('/api/activity').json())>10
    assert len(client.get('/api/alerts').json())>5
    ai=client.get('/api/ai/summary').json()
    assert ai['mode']=='trained-on-current-cohort'
    assert ai['algorithm']=='IsolationForest'
    assert ai['samples'] > 100  # sample count varies with seed size
    assert ai['findings'][0]['combined_priority']>=ai['findings'][-1]['combined_priority']
    assert len(client.get('/api/connectors/runs').json())==1
    assert client.get('/api/reports/summary').json()['activity_events']>100


def test_campaign_idempotent_and_never_overwrites_review_decision(setup):
    client,Session=setup
    first=next(x for x in client.get('/api/reviews').json() if x['review_status']=='Pending')
    response=client.post(f"/api/reviews/{first['review_id']}/decision",json={'decision':'retain','reviewer':'Research Reviewer'})
    assert response.status_code==200
    first_gen=client.post('/api/reviews/generate')
    assert first_gen.status_code==200
    assert first_gen.json()['created']>=0
    again=client.post('/api/reviews/generate')
    assert again.json()['created']==0
    all_reviews=client.get('/api/reviews').json()
    assert next(r for r in all_reviews if r['review_id']==first['review_id'])['review_status']=='Retained'


def test_csv_import_never_auto_links_and_is_idempotent(setup,tmp_path):
    client,Session=setup
    path=tmp_path/'demo.csv'
    path.write_text('external_account_id,username,account_email,permission,resource\n'+
                    'lab-unique01,unverified-lab,demo@demo.example,Admin,Linux-Dev-Server\n')
    with Session() as db:
        assert import_csv(db,path,'LIN')==1
        assert import_csv(db,path,'LIN')==0
        acct=db.scalar(select(Account).where(Account.external_account_id=='lab-unique01'))
        assert acct.identity_id is None
        grant=db.scalar(select(AccessGrant).where(AccessGrant.account_id==acct.id))
        assert grant.status=='Active'
        assert grant.last_verified_use is None
    assert any(r['source']=='CSV:LIN' for r in client.get('/api/connectors/runs').json())


def test_github_mock_only_get_and_never_maps_identity(setup):
    client,Session=setup
    requests=[]
    def handler(req):
        requests.append(req.method)
        if '/orgs/test-lab/repos' in str(req.url):
            return httpx.Response(200,json=[{'name':'my-demo-repo'}])
        if '/repos/test-lab/my-demo-repo/collaborators' in str(req.url):
            return httpx.Response(200,json=[{'id':1234567,'login':'labdev','role_name':'admin'}])
        return httpx.Response(404)
    http=httpx.Client(transport=httpx.MockTransport(handler))
    with Session() as db:
        assert sync(db,'test-lab','DEMO_FAKE_TOKEN',client=http)==1
        assert sync(db,'test-lab','DEMO_FAKE_TOKEN',client=http)==0
        account=db.scalar(select(Account).where(Account.external_account_id=='github-user:1234567'))
        assert account.identity_id is None
        grant=db.scalar(select(AccessGrant).where(AccessGrant.account_id==account.id))
        assert grant.privilege==1
    http.close()
    assert requests==['GET']*4


def test_missing_activity_is_not_asserted_as_inactive(setup):
    client,_=setup
    rows=client.get('/api/access').json()
    missing=next(x for x in rows if x['last_verified_use'] is None)
    assert any('NOT' in reason or 'not prove' in reason.lower() for reason in missing['reasons'])
    assert 'probability' in client.get('/api/ai/summary').json()['metric_note']
