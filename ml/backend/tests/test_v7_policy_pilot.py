"""V7 conservative scope controls and sampling review calibration."""
from datetime import timedelta
from uuid import uuid4
import csv
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import (Employee,Account,Entitlement,GovernedResourcePolicy,
                        GovernedResourceUse,utcnow)
from app.ml.periodic_features import aggregate_accounts
from app.ml.periodic_queue import make_review_queue
from app.ml.pilot_sampling import (freeze_blind_sample,write_blind_template,
                                    evaluate_sample,reconcile_completed_manual_reviews)


def test_governed_business_resources_only():
    engine=create_engine(f'sqlite:////tmp/aegis-v7-{uuid4().hex}.db')
    Base.metadata.create_all(engine)
    now=utcnow()
    with Session(engine) as db:
        person=Employee(code='E001',name='HR employee',email='hr@example.test',
                        department='HR',job_title='HR Analyst',status='active')
        db.add(person);db.flush()
        account=Account(employee_id=person.id,username='hr-person',platform='linux',status='active')
        db.add(account);db.flush()
        # Only company-approved business resource maps can create a finding.
        db.add(GovernedResourcePolicy(organization_key='demo',platform='linux',
                 resource_kind='managed_software',resource_key='production-db-admin',
                 allowed_departments=['IT'],allowed_job_titles=[],approved_by='company-security',
                 policy_version='2026Q4',effective_at=now-timedelta(days=100),active=True))
        db.add(GovernedResourceUse(event_key='ev1',account_id=account.id,
                 resource_kind='managed_software',resource_key='production-db-admin',
                 occurred_at=now-timedelta(days=3),source='linux-collector',
                 source_verified=True,outcome='observed'))
        # Music has no managed-business-resource policy and MUST NOT count.
        db.add(GovernedResourceUse(event_key='ev2',account_id=account.id,
                 resource_kind='managed_web_app',resource_key='music.example',
                 occurred_at=now-timedelta(days=3),source='linux-collector',
                 source_verified=True,outcome='observed'))
        # A fake/failed attempt is never proof of unauthorized access.
        db.add(GovernedResourceUse(event_key='ev3',account_id=account.id,
                 resource_kind='managed_software',resource_key='production-db-admin',
                 occurred_at=now-timedelta(days=4),source='linux-collector',
                 source_verified=False,outcome='observed'))
        db.add(GovernedResourceUse(event_key='ev4',account_id=account.id,
                 resource_kind='managed_software',resource_key='production-db-admin',
                 occurred_at=now-timedelta(days=4),source='linux-collector',
                 source_verified=True,outcome='denied'))
        db.commit()
        records=aggregate_accounts(db,as_of=now,window_days=90)
        assert records[0]['managed_policy_conflict_count']==1
        assert records[0]['managed_policy_conflict_resources'][0]['resource_key']=='production-db-admin'
        result=make_review_queue(records,review_budget_percent=100,policy_threshold=25)
        acc=result['accounts'][0]
        assert acc['policy_score']>=35
        assert acc['review_priority']=='selected'
        assert 'music' not in str(acc['reasons']).lower()
        assert acc['activity_summary']['managed_policy_conflict_count']==1
        assert acc['automatically_certified'] is False


def test_policy_unknown_or_no_explicit_scope_does_not_flag():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    now=utcnow()
    with Session(engine) as db:
        emp=Employee(code='E2',name='Employee',email='e2@example.test',department='HR',
                     job_title='Clerk',status='active')
        db.add(emp);db.flush()
        a=Account(employee_id=emp.id,username='e2',platform='windows',status='active')
        db.add(a);db.flush()
        db.add(GovernedResourcePolicy(organization_key='demo',platform='windows',
             resource_kind='business_application',resource_key='shared-calendar',
             allowed_departments=[],allowed_job_titles=[],approved_by='admin',
             policy_version='1',effective_at=now-timedelta(days=100),active=True))
        db.add(GovernedResourceUse(event_key='j1',account_id=a.id,
             resource_kind='business_application',resource_key='shared-calendar',
             occurred_at=now-timedelta(days=3),source='connector',source_verified=True,outcome='observed'))
        db.commit()
        rec=aggregate_accounts(db,as_of=now)[0]
        assert rec['managed_policy_conflict_count']==0


def frozen_records():
    return {'parameters':{'review_budget_percent':40,'policy_threshold':25,'anomaly_threshold':.95},
            'records':[{'account_id':i,'platform':'linux','mandatory':i==1,
                        'policy_score':40 if i in (1,2) else 0,
                        'anomaly_percentile':.99 if i==3 else .20}
                       for i in range(1,11)]}


def test_blind_sample_from_both_strata_and_estimated_misses(tmp_path):
    frozen=frozen_records()
    sample=freeze_blind_sample(frozen,selected_sample=2,unselected_sample=3,seed=18)
    assert len(sample['sampled_ids'])==5
    assert set(sample['private_stratum'].values())=={'selected','unselected'}
    path=tmp_path/'blind.csv'
    write_blind_template(sample,path)
    content=path.read_text()
    assert 'anomaly_percentile' not in content
    assert 'review_priority' not in content
    assert 'selected' not in content
    manual={uid:{'decision':'followup' if sample['private_stratum'][uid]=='unselected' else 'retain',
                 'reviewer':'app-owner','reason':'independent review', 'review_minutes':4}
             for uid in sample['sampled_ids']}
    result=evaluate_sample(sample,manual)
    assert result['estimated_missed_cases']>0
    assert result['estimated_recall']==0
    assert result['timed_sample_review_minutes']==20
    assert result['automatic_promotion'] is False
    with pytest.raises(ValueError):
        evaluate_sample(sample,{})


def test_deduplicate_review_work_but_keep_unresolved_mandatory():
    frozen=frozen_records()
    manual={
        '1':{'cycle_key':'Q4','verified':True,'reviewer':'owner',
             'rationale':'Reviewed', 'decision':'retain','mandatory_obligations_covered':False},
        '2':{'cycle_key':'Q4','verified':True,'reviewer':'owner',
             'rationale':'Reviewed', 'decision':'retain'},
    }
    result=reconcile_completed_manual_reviews(frozen,manual,cycle_key='Q4')
    assert '2' in result['already_reviewed_and_attested']
    assert '1' in result['still_to_review']
    manual['1']['mandatory_obligations_covered']=True
    result2=reconcile_completed_manual_reviews(frozen,manual,cycle_key='Q4')
    assert '1' in result2['already_reviewed_and_attested']


def test_managed_import_requires_company_approved_scope(tmp_path):
    from app.ml.governed_import import import_managed_csv
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
    now=utcnow()
    with Session(engine) as db:
        emp=Employee(code='EIMP',name='Analyst',email='imp@example.test',department='HR',
                     job_title='HR Analyst',status='active')
        db.add(emp);db.flush()
        db.add(Account(employee_id=emp.id,platform='Linux',username='analyst',status='active'))
        db.commit()
        pol=tmp_path/'policy.csv'
        pol.write_text('platform,resource_kind,resource_key,allowed_departments,allowed_job_titles,approved_by,policy_version,effective_at\n'
                       'Linux,managed_software,production-db-admin,IT,,security-owner,2026Q4,2026-07-01T00:00:00\n')
        with pytest.raises(ValueError):
            import_managed_csv(db,pol,kind='policy',policy_approvers=[])
        assert import_managed_csv(db,pol,kind='policy',policy_approvers=['security-owner'])['created']==1
        assert import_managed_csv(db,pol,kind='policy',policy_approvers=['security-owner'])['ignored_duplicate']==1
        events=tmp_path/'usage.csv'
        events.write_text('event_key,platform,username,resource_kind,resource_key,occurred_at,source,outcome\n'
                          'event-100,Linux,analyst,managed_software,production-db-admin,2026-10-02T00:00:00,linux-collector,observed\n'
                          'event-101,Linux,analyst,managed_web_app,personal-music,2026-10-02T00:00:00,linux-collector,observed\n')
        with pytest.raises(ValueError):
            import_managed_csv(db,events,kind='usage',trusted_sources=[])
        result=import_managed_csv(db,events,kind='usage',trusted_sources=['linux-collector'])
        assert result == {'created':1,'ignored_duplicate':0,'ignored_not_managed':1}
