"""Product requirements from the industry expert: 90-day batched review, not EDR."""
from app.ml.competition_demo import sample_three, synthetic_scale
from app.ml.periodic_queue import make_review_queue
from app.ml.periodic_generate import generate
from app.ml.periodic_model import train_periodic
from app.ml.periodic_benchmark import benchmark


def test_chamila_rishan_three_account_story():
    result=make_review_queue(sample_three(),review_budget_percent=50,artifact=None)
    by_name={i['username']:i for i in result['accounts']}
    assert result['total_accounts']==3
    assert result['selected_count']==2
    assert by_name['rishan.demo']['review_priority']=='mandatory'
    assert by_name['third.demo']['review_priority']=='selected'
    assert by_name['chamila.demo']['review_priority']=='deprioritized_not_certified'
    assert all(i['review_priority']!='certified' for i in result['accounts'])


def test_mandatory_cases_cannot_be_hidden_by_budget():
    rows=synthetic_scale(200)
    result=make_review_queue(rows,review_budget_percent=1,artifact=None)
    assert result['selected_count']>=result['mandatory_count']
    assert all(i['review_priority']=='mandatory' for i in result['accounts'] if i['employee_status']!='active')


def test_benchmark_compares_hybrid_with_rules_without_safety_claim():
    data=generate(320)
    model=train_periodic(data)
    result=benchmark(data,model,10)
    assert 'rule_only' in result and 'hybrid_rule_plus_ml' in result
    assert result['hybrid_rule_plus_ml']['recall']<=1
    assert result['hybrid_rule_plus_ml']['missed_review_needed']>=0
    assert 'NOT' not in result['validation'] or 'SYNTHETIC' in result['validation']


def test_application_owner_precedence_over_employee_line_manager(monkeypatch):
    from app.main import resolve_application_owner
    monkeypatch.setenv('PLATFORM_REVIEWERS_JSON', '{"GitHub": "app-owner"}')
    assert resolve_application_owner('GitHub', {'manager', 'app-owner'}, 'manager', 'admin') == 'app-owner'
    assert resolve_application_owner('Linux', {'manager', 'app-owner'}, 'manager', 'admin') == 'manager'
    monkeypatch.setenv('PLATFORM_REVIEWERS_JSON', '{ invalid')
    assert resolve_application_owner('GitHub', {'reviewer'}, None, 'admin') == 'reviewer'
