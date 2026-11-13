"""Tests for industry-expert input, transfer, AD-group and shadow-review feedback."""
from datetime import timedelta
from uuid import uuid4
import csv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from app.db import Base
from app.models import Employee, Account, Entitlement, ActivityCoverage, utcnow
from app.importers import import_csv
from app.ml.periodic_features import aggregate_accounts, FEATURE_SCHEMA_VERSION
from app.ml.periodic_queue import make_review_queue
from app.ml.parallel_review import compare
from app.ml.source_ingest import push_rows, rows_csv, rows_mysql


def db_engine():
    engine=create_engine(f'sqlite:////tmp/ad-feedback-{uuid4().hex}.db')
    Base.metadata.create_all(engine)
    return engine


def upload(db, kind, text):
    return import_csv(db, kind, text.encode())


def test_ad_groups_reporting_transfers_feature_and_shortlist():
    engine = db_engine()
    now = utcnow()
    window = now - timedelta(days=25)
    date = window.isoformat()
    snapshot = (now-timedelta(days=1)).isoformat()
    with Session(engine) as db:
        upload(db,'employees','code,name,email,department,job_title,status,manager_username\nE1,Test Employee,e1@example.test,Engineering,Developer,active,reviewer\n')
        upload(db,'accounts','platform,username,employee_code,status\nGitLab,employee1,E1,active\n')
        upload(db,'entitlements','platform,username,resource,permission,sensitivity\nGitLab,employee1,group:repo,write,medium\n')
        upload(db,'directory_snapshots',f'employee_code,snapshot_at,reporting_manager,org_unit,ad_department,groups_complete,transfer_history_complete,source\nE1,{snapshot},CN=New Manager,OU=Eng,Engineering,true,true,AD-export\n')
        # V6 requires an APPROVED, scoped catalog; raw 'privileged=true' is not trusted.
        upload(db, 'ad_group_catalog', 'organization_key,directory_key,group_key,display_name,group_kind,access_relevance,privilege_tier,risk_tier,approved_by,source,policy_version\ndemo,primary,name:dev-team,Dev-Team,security,non_access,standard,low,security-owner,AD-governance,v1\ndemo,primary,name:gitlab-maintainers,GitLab-Maintainers,security,access,privileged,high,security-owner,AD-governance,v1\n')
        upload(db,'ad_groups','employee_code,group_name,active,source,privileged\nE1,Dev-Team,true,AD-export,false\nE1,GitLab-Maintainers,true,AD-export,true\n')
        upload(db,'employee_transfers',f'employee_code,occurred_at,from_department,to_department,from_manager,to_manager,source\nE1,{date},Finance,Engineering,Old Manager,New Manager,HR-export\n')
        upload(db,'ad_group_changes',f'employee_code,group_name,action,occurred_at,source\nE1,GitLab-Maintainers,added,{date},AD-change-export\n')
        db.add(ActivityCoverage(platform='GitLab',event_type='resource_use',start_at=now-timedelta(days=90),end_at=now,source='test',attested_by='test'))
        db.commit()
        features = aggregate_accounts(db,as_of=utcnow())[0]
        assert features['ad_group_count']==2 and features['ad_group_data_known']==1
        assert features['privileged_ad_group_count']==1
        assert features['manager_changes_window']==1
        assert features['department_changes_window']==1
        assert features['transfers_window']==1
        assert features['group_changes_window']==1
        assert features['transfer_history_known']==1
        q=make_review_queue([{**features,'period_days':90}])
        assert q['selected_count']==1
        assert any('transferred' in r for r in q['accounts'][0]['reasons'])
        assert q['accounts'][0]['activity_summary']['employee_transfers']==1
    engine.dispose()


def test_unknown_ad_coverage_not_equivalent_to_complete_zero_groups():
    engine=db_engine()
    with Session(engine) as db:
        person=Employee(code='U',name='Unknown',email='u@example.test',department='HR',job_title='Analyst',status='active')
        db.add(person); db.flush()
        a=Account(platform='Windows',username='user',employee_id=person.id,status='active')
        db.add(a); db.flush()
        db.add(Entitlement(account_id=a.id,resource='windows:test',permission='read',sensitivity='low'))
        db.commit()
        row=aggregate_accounts(db)[0]
        assert row['ad_group_data_known']==0 and row['ad_group_count']==0
        assert row['transfer_history_known']==0
        assert row['recent_transfer_flag']==0
    engine.dispose()


def test_source_ingest_csv_batch(tmp_path, monkeypatch):
    from app.ml import source_ingest
    engine=db_engine()
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(source_ingest,'SessionLocal',sessionmaker(bind=engine))
    input_file=tmp_path/'employees.csv'
    input_file.write_text('employee_id,full_name,email,department,job_title,status\nE100,Test 100,e100@example.test,IT,Engineer,active\n',encoding='utf-8')
    assert push_rows('employees',rows_csv(input_file,{'employee_id':'code','full_name':'name'}),batch_size=1)==1
    with Session(engine) as db:
        assert db.query(Employee).filter_by(code='E100').count()==1
    engine.dispose()


def test_mysql_source_rejects_expressions_before_connecting():
    with pytest.raises(ValueError, match='identifier'):
        list(rows_mysql('mysql+pymysql://user:pass@localhost/db','users;DROP TABLE employees',{}))


def test_parallel_manual_comparison_requires_full_review(tmp_path):
    predicted=tmp_path/'frozen.csv'
    predicted.write_text('account_id,review_priority,policy_score,anomaly_percentile\n1,selected,40,\n2,deprioritized_not_certified,0,\n3,mandatory,60,\n')
    manual=tmp_path/'full.csv'
    manual.write_text('account_id,decision,review_minutes\n1,followup,3\n2,remove,4\n3,retain,2\n')
    report=compare(predicted,manual)
    assert report['manual_reviewed']==3
    assert report['recall_at_review_budget']==.5
    assert report['false_negatives']==1
    assert report['potential_minutes_outside_selected_queue']==4
    manual.write_text('account_id,decision,review_minutes\n1,followup,3\n3,retain,2\n')
    with pytest.raises(ValueError,match='ALL'):
        compare(predicted,manual)


def test_new_feature_schema_and_configurable_thresholds():
    assert 'ad' in FEATURE_SCHEMA_VERSION
    rows=[{'account_id':1,'username':'one','platform':'Linux','employee_status':'active',
           'entitlement_count':1,'outside_role_count':0,'privileged_entitlements':0,
           'sensitive_entitlements':0,'permission_changes_window':0,'transfers_window':1,
           'group_changes_window':0,'privileged_ad_group_count':0,
           'use_evidence_observed':1,'use_age_days':1,'log_coverage_days':90,
           'log_coverage_known':1}]
    assert make_review_queue(rows,policy_threshold=25)['mandatory_count']==1
    assert make_review_queue(rows,policy_threshold=100)['mandatory_count']==1

def test_change_between_two_ad_snapshots_becomes_scope_event():
    from app.models import EmployeeTransfer
    engine=db_engine()
    now=utcnow()
    first=(now-timedelta(days=35)).isoformat()
    second=(now-timedelta(days=3)).isoformat()
    with Session(engine) as db:
        upload(db,'employees','code,name,email,department,job_title,status\nE99,Example,e99@example.test,IT,Dev,active\n')
        upload(db,'accounts','platform,username,employee_code,status\nGitHub,example,E99,active\n')
        upload(db,'entitlements','platform,username,resource,permission,sensitivity\nGitHub,example,repo:sample,write,low\n')
        def snap(when, manager, department, ou):
            return ('employee_code,snapshot_at,reporting_manager,org_unit,ad_department,groups_complete,transfer_history_complete,source\n'
                    f'E99,{when},{manager},{ou},{department},true,true,AD-readonly\n')
        upload(db,'directory_snapshots',snap(first,'Manager-A','IT','OU=IT'))
        assert db.query(EmployeeTransfer).count()==0
        upload(db,'directory_snapshots',snap(second,'Manager-B','Operations','OU=OPS'))
        assert db.query(EmployeeTransfer).count()==1
        rec=aggregate_accounts(db,as_of=utcnow())[0]
        assert rec['manager_changes_window']==1
        assert rec['department_changes_window']==1
        assert rec['org_unit_changes_window']==1
        # Re-importing the same snapshot is idempotent.
        upload(db,'directory_snapshots',snap(second,'Manager-B','Operations','OU=OPS'))
        assert db.query(EmployeeTransfer).count()==1
    engine.dispose()
