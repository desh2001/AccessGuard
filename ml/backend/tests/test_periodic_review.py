"""Tests for supervisor-corrected 90-day periodic review functionality."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Employee, Account, Entitlement, Activity, ActivityCoverage, utcnow
from app.ml.periodic_features import aggregate_accounts
from app.ml.periodic_queue import make_review_queue, periodic_preview
from app.ml.periodic_model import train_periodic, predict_periodic
from app.ml.periodic_generate import generate


def demo_db():
    engine = create_engine(f'sqlite:////tmp/quarterly-{uuid4().hex}.db')
    Base.metadata.create_all(engine)
    return engine


def test_90_day_window_ignores_old_events_and_login_is_not_resource_use():
    engine=demo_db()
    now=utcnow()
    with Session(engine) as db:
        person=Employee(code='C1',name='Chamila',email='c1@x.test',department='IT',job_title='Engineer',status='active')
        db.add(person); db.flush()
        a=Account(platform='Linux',username='chamila',status='active',employee_id=person.id)
        db.add(a); db.flush()
        db.add(Entitlement(account_id=a.id,resource='linux:production',permission='read',sensitivity='medium'))
        db.add_all([
            Activity(account_id=a.id, resource='linux:production', event_type='login_success', occurred_at=now-timedelta(days=1),source='test'),
            Activity(account_id=a.id, resource='linux:production', event_type='resource_use', occurred_at=now-timedelta(days=105),source='test'),
        ])
        db.commit()
        row=aggregate_accounts(db,as_of=now)[0]
        assert row['successful_logins_window']==1
        assert row['resource_use_events_window']==0
        assert row['use_evidence_observed']==0
        assert row['log_coverage_known']==0
        preview=periodic_preview(db,as_of=now)
        result=preview['accounts'][0]
        assert any('Missing usage-collection coverage' in r for r in result['reasons'])
        assert result['review_priority'] == 'insufficient_evidence'
        assert not any('No verified resource use' in r for r in result['reasons'])
    engine.dispose()


def test_resigned_employee_mandatory_even_at_tiny_budget_without_removal():
    rows=[]
    for i in range(100):
        rows.append({
            'account_id':i+1,'username':f'user{i}', 'employee_code':f'EMP{i}',
            'platform':'Linux','department':'IT', 'employee_status':'inactive' if i==73 else 'active',
            'entitlement_count':1,'privileged_entitlements':0,'sensitive_entitlements':0,
            'outside_role_count':0,'permission_changes_window':0,
            'use_evidence_observed':1,'use_age_days':3,
            'log_coverage_days':90,'log_coverage_known':1,
            'successful_logins_window':9,'resource_use_events_window':11,'active_days_window':9,
        })
    result=make_review_queue(rows, review_budget_percent=1)
    assert result['selected_count']==1
    assert next(x for x in result['accounts'] if x['account_id']==74)['review_priority']=='mandatory'
    assert result['deprioritized_count']==99
    assert 'NOT certified' in result['non_selection_means']


def test_mandatory_review_overrides_budget():
    rows=[]
    for i in range(10):
        rows.append(dict(account_id=i, username=str(i),employee_code=None,platform='GitHub', department='Unknown',
                         employee_status='unmapped' if i<4 else 'active',entitlement_count=1,
                         privileged_entitlements=0,sensitive_entitlements=0,outside_role_count=0,
                         permission_changes_window=0,use_evidence_observed=0,use_age_days=0,
                         log_coverage_days=0,log_coverage_known=0,successful_logins_window=0,
                         resource_use_events_window=0,active_days_window=0))
    result=make_review_queue(rows,review_budget_percent=10)
    assert result['selected_count']==4
    assert result['mandatory_count']==4
    assert result['budget_exceeded_by_mandatory_cases'] is True


def test_attested_coverage_intervals_are_elapsed_time_not_touched_days():
    engine=demo_db()
    now=utcnow()
    with Session(engine) as db:
        person=Employee(code='E3',name='E',email='e3@x.test',department='IT',job_title='Engineer',status='active')
        db.add(person); db.flush()
        a=Account(platform='Linux',username='e3',status='active',employee_id=person.id)
        db.add(a); db.flush()
        db.add(Entitlement(account_id=a.id,resource='linux:vm',permission='read',sensitivity='low'))
        db.add(ActivityCoverage(platform='Linux',event_type='resource_use',start_at=now-timedelta(days=90),
                                end_at=now-timedelta(days=1),source='attested_test',attested_by='owner'))
        db.commit()
        row=aggregate_accounts(db,as_of=now)[0]
        assert row['log_coverage_known']==1
        assert row['log_coverage_days'] == 89
        result=periodic_preview(db,as_of=now)['accounts'][0]
        assert result['review_priority'] == 'insufficient_evidence'
        assert not any('No verified resource use' in x for x in result['reasons'])
    engine.dispose()


def test_periodic_model_on_synthetic_group_split_and_coverage_guard():
    data=generate(n=320)
    artifact=train_periodic(data)
    assert artifact['metadata']['evaluation']['holdout_rows'] > 0
    row=data.iloc[0].to_dict()
    predictions=predict_periodic([row],artifact)
    assert len(predictions)==1 and 0<=predictions[0]<=1
    row.update(account_id=1, username='fictional',employee_code='XX',employee_status='active',period_days=90)
    row.update(log_coverage_days=0,log_coverage_known=0)
    result=make_review_queue([row],artifact=artifact)
    assert result['ml_model_loaded'] is True
    assert result['ml_model_used'] is False
    assert result['accounts'][0]['anomaly_percentile'] is None


def test_never_fill_queue_with_normal_accounts_merely_to_hit_budget():
    from app.ml.competition_demo import row
    rows = [row(i + 1, f'normal-{i}', used=True, coverage=90) for i in range(100)]
    result = make_review_queue(rows, review_budget_percent=20)
    assert result['target_review_capacity'] == 20
    assert result['candidate_count'] == 0
    assert result['selected_count'] == 0
    assert result['deprioritized_count'] == 100
    assert all(not a['automatically_certified'] for a in result['accounts'])


def test_missing_telemetry_is_not_automatically_cleared_or_analyzed_as_zero_use():
    from app.ml.competition_demo import row
    one = row(1, 'unknown-telemetry', used=False, coverage=0)
    result = make_review_queue([one], 10)
    assert result['insufficient_evidence_count'] == 1
    assert result['selected_count'] == 0
    assert result['deprioritized_count'] == 0
    assert result['accounts'][0]['review_priority'] == 'insufficient_evidence'
    assert not any('No verified resource use during' in reason for reason in result['accounts'][0]['reasons'])


def test_mandatory_and_candidate_backlog_are_separate_from_low_priority():
    from app.ml.competition_demo import row
    rows = [row(1, 'terminated', status='inactive', used=False),
            row(2, 'mismatched', unusual=True, used=False),
            row(3, 'stale', used=False),
            row(4, 'routine', used=True)]
    result = make_review_queue(rows, review_budget_percent=25)
    assert result['target_review_capacity'] == 1
    assert result['selected_count'] == 1
    assert result['mandatory_count'] == 1
    assert result['deferred_candidate_count'] == 2
    assert result['deprioritized_count'] == 1
    assert all(a['review_priority'] != 'deprioritized_not_certified' for a in result['accounts'] if a['username'] in ('stale', 'mismatched'))


def test_exact_coverage_can_support_no_verified_use_but_not_auto_revoke():
    from app.ml.competition_demo import row
    one = row(1, 'observed-no-use', used=False, coverage=90)
    result = make_review_queue([one], 10)
    assert result['selected_count'] == 1
    assert any('No verified resource use' in r for r in result['accounts'][0]['reasons'])
    assert result['accounts'][0]['automatically_certified'] is False


def test_evidence_window_excludes_future_event_and_uses_db_side_grouping():
    engine = demo_db()
    now = utcnow()
    with Session(engine) as db:
        emp = Employee(code='DBE', name='Test', email='dbe@x.test', department='IT', job_title='Engineer')
        db.add(emp); db.flush()
        acc = Account(platform='Linux', username='dbe', employee_id=emp.id)
        db.add(acc); db.flush()
        db.add(Entitlement(account_id=acc.id, resource='linux:vm', permission='read'))
        db.add_all([
            Activity(account_id=acc.id, resource='linux:vm', event_type='resource_use', occurred_at=now+timedelta(days=1), source='test'),
            Activity(account_id=acc.id, resource='linux:vm', event_type='login_success', occurred_at=now-timedelta(days=2), source='test'),
            Activity(account_id=acc.id, resource='linux:vm', event_type='resource_use', occurred_at=now-timedelta(days=3), source='test'),
        ])
        db.commit()
        rec = aggregate_accounts(db, as_of=now)[0]
        assert rec['resource_use_events_window'] == 1
        assert rec['successful_logins_window'] == 1
        assert rec['distinct_resources_used_window'] == 1
        assert rec['use_age_days'] == 3
    engine.dispose()


def test_unrelated_resource_activity_cannot_prove_active_grant_is_used():
    engine = demo_db()
    now = utcnow()
    with Session(engine) as db:
        emp = Employee(code='UNR', name='Test', email='unr@x.test', department='IT', job_title='Engineer')
        db.add(emp); db.flush()
        acc = Account(platform='Linux', username='unr', employee_id=emp.id)
        db.add(acc); db.flush()
        db.add(Entitlement(account_id=acc.id, resource='linux:production', permission='admin',
                           last_used_at=now-timedelta(days=3), evidence_source=None))
        db.add(Activity(account_id=acc.id, resource='unrelated:other', event_type='resource_use',
                        occurred_at=now-timedelta(days=2), source='test'))
        db.commit()
        r = aggregate_accounts(db, as_of=now)[0]
        assert r['resource_use_events_window'] == 0
        assert r['use_evidence_observed'] == 0
    engine.dispose()
