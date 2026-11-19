"""Integration tests for Enterprise Simulator Test Environment."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient
from main import app
from database import get_session
from models import Base, Identity, Account, AccessGrant, ActivityEvent, TestScenarioResult
from seed_demo import seed_demo


@pytest.fixture
def sim_client(tmp_path):
    db_file = tmp_path / 'sim_test.db'
    engine = create_engine(f'sqlite+pysqlite:///{db_file}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        seed_demo(session)
    def override():
        with Session() as session:
            yield session
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_simulator_health(sim_client):
    response = sim_client.get('/api/simulator/health')
    assert response.status_code == 200
    data = response.json()
    assert 'online' in data
    assert 'url' in data


def test_environment_isolation_stats(sim_client):
    prod_res = sim_client.get('/api/overview?env=production')
    test_res = sim_client.get('/api/overview?env=test')
    assert prod_res.status_code == 200
    assert test_res.status_code == 200
    
    prod_data = prod_res.json()
    test_data = test_res.json()
    
    # Systems in test should have SIM_ prefix, prod should not
    for s in prod_data['systems']:
        assert not s['id'].startswith('SIM_')
    for s in test_data['systems']:
        assert s['id'].startswith('SIM_')


def test_scenarios_listing(sim_client):
    response = sim_client.get('/api/simulator/scenarios')
    assert response.status_code == 200
    scenarios = response.json()
    assert len(scenarios) >= 5
    ids = [s['id'] for s in scenarios]
    assert 'scen-gov-privcreep' in ids
    assert 'scen-auth-bruteforce' in ids
    assert 'scen-gov-orphan' in ids
