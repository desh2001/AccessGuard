"""Integration tests for Enterprise Simulator Test Environment."""
import pytest
from starlette.testclient import TestClient
from main import app
from database import get_session
from models import Identity, Account, AccessGrant, ActivityEvent, TestScenarioResult

client = TestClient(app)


def test_simulator_health():
    response = client.get('/api/simulator/health')
    assert response.status_code == 200
    data = response.json()
    assert 'online' in data
    assert 'url' in data


def test_environment_isolation_stats():
    prod_res = client.get('/api/overview?env=production')
    test_res = client.get('/api/overview?env=test')
    assert prod_res.status_code == 200
    assert test_res.status_code == 200
    
    prod_data = prod_res.json()
    test_data = test_res.json()
    
    # Systems in test should have SIM_ prefix, prod should not
    for s in prod_data['systems']:
        assert not s['id'].startswith('SIM_')
    for s in test_data['systems']:
        assert s['id'].startswith('SIM_')


def test_scenarios_listing():
    response = client.get('/api/simulator/scenarios')
    assert response.status_code == 200
    scenarios = response.json()
    assert len(scenarios) >= 5
    ids = [s['id'] for s in scenarios]
    assert 'scen-gov-privcreep' in ids
    assert 'scen-auth-bruteforce' in ids
    assert 'scen-gov-orphan' in ids
