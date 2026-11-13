"""V6 regression: source-specific semantics, mandatory transfers, shadow evidence."""
from __future__ import annotations
from datetime import timedelta
from uuid import uuid4
import csv
import json
import pytest
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (Employee, Account, Entitlement, EmployeeTransfer,
                        ADGroupMembership, ADGroupCatalog, TransferAccessDisposition, utcnow)
from app.importers import import_csv
from app.ml.periodic_features import aggregate_accounts
from app.ml.periodic_queue import make_review_queue
from app.ml.enterprise_pilot import (measure, load_manual, load_frozen, hash_payload,
                                    calibrate, wilson_upper, selection)
from app.ml.enterprise_monitor import monitor
from app.ml.periodic_generate import generate


def engine_new():
    engine=create_engine(f'sqlite:////tmp/aegis-v6-{uuid4().hex}.db')
    Base.metadata.create_all(engine)
    return engine


def seeded(db):
    e=Employee(code='EMP1',name='Sample',email='s1@example.test',department='Finance',
               job_title='Accountant',status='active')
    db.add(e);db.flush()
    a=Account(platform='GitLab',username='employee1',employee_id=e.id,status='active')
    b=Account(platform='Linux',username='employee1',employee_id=e.id,status='active')
    db.add_all([a,b]);db.flush()
    db.add(Entitlement(account_id=a.id,resource='repo:budget',permission='write',sensitivity='low'))
    db.commit()
    return e.id,a.id,b.id


def test_group_catalog_per_company_directory_with_unknowns_and_nonaccess():
    engine=engine_new()
    with Session(engine) as db:
        eid,aid,_=seeded(db)
        csv_data='''organization_key,directory_key,group_key,display_name,group_kind,access_relevance,privilege_tier,risk_tier,approved_by,source,policy_version,allowed_departments
company-A,ad-1,S-1-100,Money-Team,security,access,privileged,critical,Security-Owner,approved-policy,v1,IT
company-B,ad-1,S-1-100,Money-Team,distribution,non_access,standard,low,Security-Owner,approved-policy,v1,Finance
company-A,ad-1,S-1-200,Mail-List,distribution,non_access,standard,low,Security-Owner,approved-policy,v1,
'''
        assert import_csv(db,'ad_group_catalog',csv_data.encode())==3
        memberships='''employee_code,group_name,active,source,organization_key,directory_key,group_key,privileged
EMP1,Money-Team,true,AD,company-A,ad-1,S-1-100,false
EMP1,Money-Team,true,AD,company-B,ad-1,S-1-100,true
EMP1,Mail-List,true,AD,company-A,ad-1,S-1-200,true
EMP1,Unknown-Group,true,AD,company-A,ad-1,S-1-300,true
'''
        assert import_csv(db,'ad_groups',memberships.encode())==4
        row=next(x for x in aggregate_accounts(db) if x['account_id']==aid)
        assert row['ad_group_count']==4
        assert row['privileged_ad_group_count']==1  # approved only in company A
        assert row['mapped_access_ad_group_count']==1
        assert row['non_access_ad_group_count']==2
        assert row['unmapped_ad_group_count']==1
        assert row['out_of_scope_ad_group_count']==1
        assert row['group_catalog_coverage_fraction']==.75
        reviewed=make_review_queue([{**row,'period_days':90}])['accounts'][0]
        assert any('Unclassified AD groups' in x for x in reviewed['reasons'])
        assert any('incompatible with current department' in x for x in reviewed['reasons'])
    engine.dispose()


def test_every_pending_transfer_mandatory_after_window_even_with_no_entitlement():
    engine=engine_new(); now=utcnow()
    with Session(engine) as db:
        eid,aid,bid=seeded(db)
        transfer=EmployeeTransfer(employee_id=eid,occurred_at=now-timedelta(days=135),
                                   from_department='IT',to_department='Finance',source='hr')
        db.add(transfer);db.commit()
        rows=aggregate_accounts(db,as_of=now)
        assert len(rows)==2, 'Even account with no grants needs identity transfer review'
        result=make_review_queue([{**row,'period_days':90} for row in rows],review_budget_percent=.5,
                                 policy_threshold=100)
        assert result['mandatory_count']==2
        assert result['budget_exceeded_by_mandatory_cases'] is True
        assert all(r['review_priority']=='mandatory' for r in result['accounts'])
        # One application is reviewed; the other must remain pending.
        db.add(TransferAccessDisposition(transfer_id=transfer.id,account_id=aid,decision='approved_retain',
                     reviewed_by='system_owner',reviewed_at=now,rationale='Business need confirmed'))
        db.commit()
        rows=aggregate_accounts(db,as_of=now+timedelta(seconds=1))
        status={r['account_id']:r['pending_transfer_count'] for r in rows}
        assert status[aid]==0 and status[bid]==1
        q=make_review_queue([{**r,'period_days':90} for r in rows],policy_threshold=100)
        priorities={r['account_id']:r['review_priority'] for r in q['accounts']}
        assert priorities[bid]=='mandatory'
        assert priorities[aid]!='mandatory'
    engine.dispose()


def test_transfer_in_window_never_dropped_by_threshold():
    row={'account_id':21,'username':'someone','platform':'GitHub','employee_status':'active',
         'transfers_window':1,'pending_transfer_count':1,'pending_transfer_ids':[99],
         'log_coverage_known':1,'log_coverage_days':90,'period_days':90,
         'use_evidence_observed':1,'use_age_days':1}
    for threshold in [0,25,100]:
        q=make_review_queue([row],review_budget_percent=1,policy_threshold=threshold,
                            anomaly_threshold=1)
        assert q['mandatory_count']==1
        assert q['accounts'][0]['pending_transfer_ids']==[99]


def pilot_fixture(tmp_path):
    records=[
       {'account_id':i,'platform':'GitHub','review_priority':'mandatory' if i==1 else 'selected' if i==2 else 'deprioritized_not_certified',
        'mandatory':i==1,'policy_score':60 if i==1 else 30 if i==2 else 0,
        'anomaly_percentile':.99 if i==2 else .2,
        'evidence_gap':False,'reasons':[], 'pending_transfer_count':1 if i==1 else 0}
       for i in range(1,6)]
    payload={'schema':'aegis-shadow-pilot-1.0','parameters':{
        'review_budget_percent':40,'policy_threshold':25,'anomaly_threshold':.95},
        'records':records}
    frozen=tmp_path/'frozen.json'
    frozen.write_text(json.dumps({'payload':payload,'sha256':hash_payload(payload)}))
    manual=tmp_path/'manual.csv'
    manual.write_text('account_id,decision,review_minutes,severity,reviewer,reason\n'
                      '1,remove,4,critical,independent1,left company\n'
                      '2,retain,5,low,independent1,appropriate access\n'
                      '3,followup,7,high,independent1,unexpected access\n'
                      '4,retain,2,low,independent1,valid access\n'
                      '5,retain,3,low,independent1,valid access\n')
    return frozen,manual


def test_shadow_manual_all_records_required_and_critical_misses_visible(tmp_path):
    from app.ml.enterprise_pilot import evaluate
    frozen,manual=pilot_fixture(tmp_path)
    m=evaluate(frozen,manual)
    assert m['manual_positive']==2
    assert m['false_negatives']==1
    assert m['missed_critical']==0
    assert m['missed_high_or_critical']==1
    assert m['recall']==.5
    assert m['fnr_wilson_95pct_upper']>.5
    assert m['manual_total_minutes']==21
    assert m['hypothetical_minutes_outside_queue']==12
    # Missing a manual account invalidates the entire comparison.
    manual.write_text(manual.read_text().replace('5,retain,3,low,independent1,valid access\n',''))
    with pytest.raises(ValueError,match='100%'):
        evaluate(frozen,manual)
    # A changed prediction must invalidate the cryptographic digest.
    j=json.loads(frozen.read_text());j['payload']['records'][0]['policy_score']=0
    frozen.write_text(json.dumps(j))
    with pytest.raises(ValueError,match='hash mismatch'):
        evaluate(frozen,manual)


def test_pilot_calibration_needs_explicit_acceptable_miss_rate(tmp_path):
    frozen,manual=pilot_fixture(tmp_path)
    with pytest.raises(ValueError,match='explicit'):
        calibrate(frozen,manual,budgets=[20],policies=[25],anomalies=[.95],
                  max_missed_case_rate=None)
    result=calibrate(frozen,manual,budgets=[20],policies=[25],anomalies=[.95],
                  max_missed_case_rate=0)
    assert result['status']=='no_setting_met_safety_targets'
    result=calibrate(frozen,manual,budgets=[40,100],policies=[25],anomalies=[.1,.95],
                  max_missed_case_rate=0)
    assert result['status']=='candidate_requires_untouched_pilot_B'
    assert result['calibration_only'] is True


def test_ml_monitor_does_not_retrain_and_flags_unknown_groups():
    reference=generate(320,seed=23)
    current=reference.head(150).copy()
    current['resource_use_events_window']=current['resource_use_events_window']+120
    current['ad_group_count']=20
    current['unmapped_ad_group_count']=15
    data=monitor(reference,current,min_reference=100)
    assert data['catalog_mapping_alert'] is True
    assert data['unmapped_ad_group_membership_share']>.7
    assert data['features_with_psi_warning']


def test_group_catalog_rejects_unapproved_semantics():
    engine=engine_new()
    with Session(engine) as db:
        bad='organization_key,directory_key,group_key,display_name,group_kind,access_relevance,privilege_tier,risk_tier,approved_by,source,policy_version\nacme,ad1,S-01,Mail,distribution,non_access,privileged,high,owner,from-file,v1\n'
        from fastapi import HTTPException
        with pytest.raises(HTTPException,match='Non-access'):
            import_csv(db,'ad_group_catalog',bad.encode())
        assert db.query(ADGroupCatalog).count()==0
    engine.dispose()


def test_ad_membership_temporal_replay_uses_last_snapshot_at_as_of():
    engine=engine_new()
    from app.models import ADGroupMembershipHistory
    from datetime import datetime
    first=datetime(2026,9,1);second=datetime(2026,10,10)
    with Session(engine) as db:
        eid,aid,_=seeded(db)
        db.add(ADGroupMembershipHistory(employee_id=eid,organization_key='demo',
             directory_key='primary',group_key='S-R1',display_name='FinanceRole',
             active=True,observed_at=first,source='AD-export'))
        db.add(ADGroupMembershipHistory(employee_id=eid,organization_key='demo',
             directory_key='primary',group_key='S-R1',display_name='FinanceRole',
             active=False,observed_at=second,source='AD-export'))
        db.commit()
        old=next(x for x in aggregate_accounts(db,as_of=datetime(2026,9,20)) if x['account_id']==aid)
        new=next(x for x in aggregate_accounts(db,as_of=datetime(2026,11,1)) if x['account_id']==aid)
        assert old['ad_group_count']==1
        assert new['ad_group_count']==0
    engine.dispose()


def test_shadow_pilot_hmac_mode_and_invalid_signature(tmp_path,monkeypatch):
    from app.ml.enterprise_pilot import evaluate
    frozen,manual=pilot_fixture(tmp_path)
    monkeypatch.setenv('AEGIS_PILOT_SIGNING_KEY','test-pilot-signing-secret')
    with pytest.raises(ValueError,match='signature'):
        evaluate(frozen,manual)
    doc=json.loads(frozen.read_text())
    from hashlib import sha256
    import hmac
    doc['hmac_sha256']=hmac.new(b'test-pilot-signing-secret',doc['sha256'].encode(),sha256).hexdigest()
    frozen.write_text(json.dumps(doc))
    assert evaluate(frozen,manual)['recall']==.5
    monkeypatch.setenv('AEGIS_PILOT_SIGNING_KEY','wrong-secret')
    with pytest.raises(ValueError,match='signature'):
        evaluate(frozen,manual)


def test_model_provenance_hmac_roundtrip_and_tamper(tmp_path,monkeypatch):
    from app.ml.periodic_model import train_periodic,save_periodic,load_periodic
    monkeypatch.setenv('AEGIS_MODEL_SIGNING_KEY','test-private-key')
    monkeypatch.setenv('AEGIS_REQUIRE_SIGNED_MODELS','true')
    path=tmp_path/'periodic_review_model.joblib'
    monkeypatch.setenv('PERIODIC_ML_MODEL_PATH',str(path))
    model=train_periodic(generate(240,seed=9))
    save_periodic(model)
    assert load_periodic()['schema']==model['schema']
    metadata=json.loads(path.with_suffix('.json').read_text())
    assert metadata.get('artifact_hmac_sha256')
    path.write_bytes(path.read_bytes()+b'bad')
    with pytest.raises(ValueError,match='digest mismatch'):
        load_periodic()


def test_account_review_decision_records_transfer_disposition_in_same_db():
    from app.main import decide_cycle_account, DecideInput
    from app.models import (User, PeriodicReviewCycle, PeriodicAccountReview, Audit)
    engine=engine_new(); now=utcnow()
    with Session(engine) as db:
        eid,aid,_=seeded(db)
        event=EmployeeTransfer(employee_id=eid,occurred_at=now-timedelta(days=6),
                     from_department='IT',to_department='Finance',source='HR')
        db.add(event); db.flush()
        c=PeriodicReviewCycle(review_window_days=90,review_budget_percent=10,
            window_end_at=now,created_by='admin',total_accounts=1,selected_accounts=1,
            mandatory_accounts=1,model_used=False)
        db.add(c);db.flush()
        t=PeriodicAccountReview(cycle_id=c.id,account_id=aid,assigned_to='reviewer',
                priority='mandatory',policy_score=50,
                evidence_snapshot={'pending_transfer_ids':[event.id]},state='pending')
        db.add(t);db.flush()
        reviewer=User(username='reviewer',role='reviewer',display_name='Test',password_hash='x')
        answer=decide_cycle_account(t.id,DecideInput(decision='retain',
                      reason='Line manager verified continuing business need'),db,reviewer)
        assert answer['state']=='approved_retain'
        assert db.query(TransferAccessDisposition).filter_by(transfer_id=event.id,account_id=aid).count()==1
        assert db.query(Audit).filter_by(action='PERIODIC_ACCOUNT_DECIDED').count()==1
        assert next(x for x in aggregate_accounts(db,as_of=utcnow()) if x['account_id']==aid)['pending_transfer_count']==0
    engine.dispose()
