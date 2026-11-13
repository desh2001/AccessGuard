"""Competition storyboard using fictional accounts (NOT production or real employees).

Runs without a database so teams can demonstrate the mixed-source queue.
Command: python -m app.ml.competition_demo --accounts 1200 --budget 10 --with-ml
At large scale, the simulator assesses in-memory queue generation, not the API/DB.
"""
import argparse
import json
import random
import time
from .periodic_queue import make_review_queue
from .periodic_features import FEATURE_COLUMNS, CATEGORICAL


def row(account_id, username, status='active', department='IT', privileged=0,
        unusual=False, used=True, coverage=90, platform='Linux'):
    data = {
        'account_id':account_id,'username':username,'employee_code':f'DEMO-{account_id:05d}',
        'employee_status':status,'account_status':'active','platform':platform,
        'department':department,'account_type':'human',
        'permission_profile':'privileged' if privileged else 'standard',
        'entitlement_count':2,'privileged_entitlements':privileged,
        'sensitive_entitlements':int(privileged>0),'outside_role_count':int(unusual),
        'successful_logins_window':18 if used else 0,'failed_logins_window':2,
        'resource_use_events_window':24 if used else 0,'active_days_window':15 if used else 0,
        'distinct_resources_used_window':2 if used else 0,'permission_changes_window':0,
        'use_age_days':3 if used else 0,'use_evidence_observed':int(used),
        'resource_uses_month_1':8 if used else 0,
        'resource_uses_month_2':8 if used else 0,
        'resource_uses_month_3':8 if used else 0,
        'log_coverage_days':coverage,'log_coverage_known':int(coverage>0),'period_days':90,
    }
    # Keep the fictional demonstration in lockstep with trained ML schema.
    for feature in FEATURE_COLUMNS:
        data.setdefault(feature, 'unknown' if feature in CATEGORICAL else 0)
    return data


def sample_three():
    return [row(1,'chamila.demo',used=True),
            row(2,'rishan.demo',status='inactive',privileged=1,used=False),
            row(3,'third.demo',department='Finance',privileged=1,unusual=True,used=False)]


def synthetic_scale(n,seed=42):
    if n<3:raise ValueError('Need at least 3 accounts')
    rng=random.Random(seed)
    rows=sample_three()
    for i in range(4,n+1):
        status='inactive' if rng.random()<.008 else 'active'
        privilege=int(rng.random()<.07)
        unusual=bool(rng.random()<.02)
        has_usage=rng.random()<.88
        coverage=90 if rng.random()<.85 else 0
        platform = rng.choice(['Windows AD', 'Linux', 'GitHub'])
        sample = row(i, f'demo-user-{i:05d}', status=status,
                     department='Finance' if unusual else 'IT',
                     privileged=privilege, unusual=unusual, used=has_usage,
                     coverage=coverage, platform=platform)
        # Fictional declining-usage cases are not automatically removed.
        if has_usage and rng.random() < .025:
            sample.update(resource_uses_month_1=15, resource_uses_month_2=9,
                          resource_uses_month_3=0, use_age_days=45)
        rows.append(sample)
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--accounts',type=int,default=3)
    parser.add_argument('--budget',type=float,default=50.0)
    parser.add_argument('--with-ml',action='store_true',help='Run trained periodic Isolation Forest in advisory/shortlist mode (synthetic, no real validation)')
    args=parser.parse_args()
    from .platform_models import load_all_platforms, SUPPORTED_MODELS
    models = load_all_platforms() if args.with_ml else {}
    if args.with_ml and set(models) != set(SUPPORTED_MODELS):
        parser.error('Train all three models first: python -m app.ml.platform_train')
    rows=sample_three() if args.accounts==3 else synthetic_scale(args.accounts)
    start=time.perf_counter()
    outcome=make_review_queue(rows,args.budget,platform_models=models)
    duration=time.perf_counter()-start
    summary={k:v for k,v in outcome.items() if k!='accounts'}
    summary['scenario']='FICTIONAL competition demonstration'
    summary['in_memory_ranking_seconds']=round(duration,3)
    summary['ml_requested']=args.with_ml
    summary['performance_warning']='Synthetic in-memory queue only; excludes real database throughput, API latency, and source log parsing.'
    summary['example_accounts']=[{k:v for k,v in record.items() if k in
        ('username','review_priority','policy_score','reasons')} for record in
        outcome['accounts'] if record['account_id'] in (1,2,3)]
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
