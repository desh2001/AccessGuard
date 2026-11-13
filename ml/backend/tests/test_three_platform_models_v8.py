"""V8 regression coverage for platform-specific ML routing and source semantics."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Employee, Account, Activity, Entitlement, ActivityCoverage, utcnow
from app.ml.periodic_features import aggregate_accounts
from app.ml.periodic_generate import generate
from app.ml.periodic_queue import make_review_queue
from app.ml.platform_models import (
    SUPPORTED_MODELS, platform_key, prepare_platform, train_all_platforms,
    save_platform, load_platform, predict_platform, MODEL_SCHEMA_VERSION,
)


@pytest.fixture(scope="module")
def trained():
    return train_all_platforms(generate(900, seed=19), seed=42, n_estimators=50)


def test_three_independent_models_and_features(trained):
    assert set(trained) == set(SUPPORTED_MODELS)
    assert all(a['pipeline'] is not b['pipeline'] for i,a in enumerate(trained.values())
               for j,b in enumerate(trained.values()) if i != j)
    assert 'windows_privileged_logon_events' in trained['windows']['metadata']['features']
    assert 'windows_privileged_logon_events' not in trained['linux']['metadata']['features']
    assert 'linux_sudo_events' in trained['linux']['metadata']['features']
    assert 'github_repo_activity_events' in trained['github']['metadata']['features']
    assert trained['github']['schema'] == MODEL_SCHEMA_VERSION
    assert platform_key('Windows AD') == 'windows'
    assert platform_key('Ubuntu') == 'linux'
    assert platform_key('GitHub Enterprise') == 'github'
    assert platform_key('GitLab') is None, 'GitLab must not silently use a GitHub model'


def test_router_separates_all_three_and_never_scores_unknown_or_no_coverage(trained):
    records=[]
    per_platform = {'windows':'Windows AD','linux':'Linux','github':'GitHub'}
    sample=generate(900, seed=19)
    for i, (key, source) in enumerate(per_platform.items()):
        record=sample.loc[sample.platform == source].iloc[i].to_dict()
        record.update(account_id=i+1, username=f'{key}-user', employee_code=f'{key}-employee',
                      employee_status='active', log_coverage_days=90, log_coverage_known=1,
                      period_days=90)
        records.append(record)
    unknown={**records[2], 'platform':'GitLab', 'account_id':4, 'username':'gitlab-user'}
    missing={**records[1], 'account_id':5, 'username':'linux-gap',
             'log_coverage_days':0,'log_coverage_known':0}
    transfer={**records[0], 'account_id':6, 'username':'mandatory-transfer',
              'pending_transfer_count':1,'pending_transfer_ids':[99]}
    result=make_review_queue(records+[unknown,missing,transfer], 5,
                             policy_threshold=100, anomaly_threshold=1,
                             platform_models=trained)
    indexed={r['account_id']:r for r in result['accounts']}
    assert [indexed[i]['ml_model_key'] for i in (1,2,3)] == ['windows','linux','github']
    assert all(indexed[i]['anomaly_percentile'] is not None for i in (1,2,3))
    assert indexed[4]['ml_model_key'] is None
    assert indexed[4]['anomaly_percentile'] is None
    assert indexed[5]['ml_model_key'] is None
    assert indexed[5]['anomaly_percentile'] is None
    assert indexed[5]['review_priority'] == 'insufficient_evidence'
    assert indexed[6]['review_priority'] == 'mandatory'
    assert indexed[6]['pending_transfer_ids'] == [99]
    assert result['platform_model_scored'] == {'windows':2,'linux':1,'github':1}
    assert result['unsupported_platform_accounts'] == 1


def test_wrong_platform_cannot_enter_another_model(trained):
    row=generate(900, seed=19).query("platform == 'Linux'").iloc[0].to_dict()
    with pytest.raises(ValueError, match='not belonging'):
        prepare_platform([row], 'github')
    with pytest.raises(ValueError, match='not belonging'):
        predict_platform([row], trained['windows'])


def test_source_event_counts_are_context_not_permission_use():
    db_engine=create_engine(f'sqlite:////tmp/aegis-v8-test-{uuid4().hex}.db')
    Base.metadata.create_all(db_engine)
    now=utcnow()
    with Session(db_engine) as db:
        for p,name,kind in [('Windows AD','w1','windows_privileged_logon'),
                            ('Linux','l1','linux_sudo'),
                            ('GitHub','g1','github_repo_activity')]:
            person=Employee(code=name,name=name,email=f'{name}@test.invalid',department='IT',job_title='Engineer',status='active')
            db.add(person);db.flush()
            acc=Account(platform=p,username=name,status='active',employee_id=person.id)
            db.add(acc);db.flush()
            db.add(Entitlement(account_id=acc.id,resource=f'{p}:sensitive',permission='read',active=True))
            db.add(Activity(account_id=acc.id,resource=f'{p}:sensitive',event_type=kind,
                            occurred_at=now-timedelta(days=2),source='source-normalizer'))
            db.add(ActivityCoverage(platform=p,event_type=kind,
                start_at=now-timedelta(days=90),end_at=now,source='test',attested_by='owner'))
            db.add(ActivityCoverage(platform=p,event_type='resource_use',
                start_at=now-timedelta(days=90),end_at=now,source='test',attested_by='owner'))
        # Personal browsing does not become resource-use or access-policy finding.
        linux=db.query(Account).filter_by(platform='Linux',username='l1').first()
        db.add(Activity(account_id=linux.id,resource='music-website',event_type='browser_visit',
                        occurred_at=now-timedelta(days=1),source='test'))
        db.commit()
        rows={r['platform']:r for r in aggregate_accounts(db,as_of=now)}
        assert rows['Windows AD']['windows_privileged_logon_events'] == 1
        assert rows['Windows AD']['windows_privileged_logon_coverage_known'] == 1
        assert rows['Linux']['linux_sudo_events'] == 1
        assert rows['Linux']['linux_sudo_coverage_known'] == 1
        assert rows['GitHub']['github_repo_activity_events'] == 1
        assert rows['GitHub']['github_repo_activity_coverage_known'] == 1
        assert all(row['resource_use_events_window'] == 0 for row in rows.values())
        assert all(row['use_evidence_observed'] == 0 for row in rows.values())
    db_engine.dispose()


def test_model_artifacts_are_platform_bound_and_integrity_checked(tmp_path,trained):
    path=tmp_path/'windows.joblib'
    save_platform(trained['windows'],path)
    restored=load_platform('windows',path)
    assert restored['model_key'] == 'windows'
    with pytest.raises(ValueError,match='Wrong platform|incompatible'):
        load_platform('linux',path)
    path.write_bytes(path.read_bytes()+b'tampered')
    with pytest.raises(ValueError,match='Tampered'):
        load_platform('windows',path)


def test_normalized_source_coverage_import_accepts_matching_platform_only():
    from app.importers import import_csv
    from fastapi import HTTPException
    db_engine=create_engine(f'sqlite:////tmp/aegis-v8-cov-{uuid4().hex}.db')
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as db:
        header='platform,event_type,start_at,end_at,source,attested_by\n'
        base='2026-08-01T00:00:00,2026-08-02T00:00:00,collector,system-owner\n'
        valid=header + ('Windows AD,windows_privileged_logon,'+base) + (
            'Linux,linux_sudo,'+base) + ('GitHub,github_repo_activity,'+base)
        assert import_csv(db,'coverage',valid.encode()) == 3
        with pytest.raises(HTTPException):
            import_csv(db,'coverage',(header+'GitHub,linux_sudo,'+base).encode())
    db_engine.dispose()


def test_end_to_end_database_preview_routes_to_three_models(tmp_path,monkeypatch,trained):
    from app.ml.periodic_queue import periodic_preview
    monkeypatch.setenv('AEGIS_PLATFORM_MODEL_DIR',str(tmp_path))
    for key, artifact in trained.items():
        save_platform(artifact, tmp_path/f'{key}.joblib')
    db_engine=create_engine(f'sqlite:////tmp/aegis-v8-api-{uuid4().hex}.db')
    Base.metadata.create_all(db_engine)
    now=utcnow()
    with Session(db_engine) as db:
        for p,name in [('Windows AD','w2'),('Linux','l2'),('GitHub','g2')]:
            emp=Employee(code=name,name=name,email=f'{name}@test.invalid',
                         department='Engineering',job_title='Engineer',status='active')
            db.add(emp);db.flush()
            acc=Account(platform=p,username=name,employee_id=emp.id,status='active')
            db.add(acc);db.flush()
            db.add(Entitlement(account_id=acc.id,resource=f'{p}:resource',permission='read',active=True))
            db.add(Activity(account_id=acc.id,resource=f'{p}:resource',
                            event_type='resource_use',occurred_at=now-timedelta(days=1),source='trusted-adapter'))
            db.add(ActivityCoverage(platform=p,event_type='resource_use',
                                    start_at=now-timedelta(days=90),end_at=now,
                                    source='test',attested_by='source-owner'))
        db.commit()
        result=periodic_preview(db,as_of=now,max_results=10)
        accounts={a['platform']:a for a in result['accounts']}
        assert accounts['Windows AD']['ml_model_key']=='windows'
        assert accounts['Linux']['ml_model_key']=='linux'
        assert accounts['GitHub']['ml_model_key']=='github'
        assert all(a['anomaly_percentile'] is not None for a in accounts.values())
        assert result['platform_model_scored']=={'windows':1,'linux':1,'github':1}
        assert not any(a['automatically_certified'] for a in accounts.values())
    db_engine.dispose()
