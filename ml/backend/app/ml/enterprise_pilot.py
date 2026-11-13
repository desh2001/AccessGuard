"""Independent, offline shadow pilot and human-label threshold calibration.

The full manual review is the temporary reference standard. ML predictions are
frozen BEFORE manual decisions; nothing is promoted or automatically certified.

Usage examples in ENTERPRISE_ML_V6_GUIDE.md.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import hmac
import os
import json
from math import ceil, sqrt
from pathlib import Path
from itertools import product
from app.db import SessionLocal
from .periodic_queue import periodic_preview

POSITIVE = {'remove', 'followup'}
DECISIONS = {'retain', *POSITIVE}
SEVERITIES = {'critical', 'high', 'medium', 'low'}


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8')


def hash_payload(payload):
    return hashlib.sha256(canonical(payload)).hexdigest()


def freeze_to_file(path: Path, manual_template: Path, *, budget=10.0, policy=25, anomaly=.95):
    with SessionLocal() as db:
        preview = periodic_preview(db, window_days=90, review_budget_percent=budget,
                                   policy_threshold=policy, anomaly_threshold=anomaly)
    records = []
    for item in preview['accounts']:
        records.append({k:item[k] for k in (
            'account_id','platform','review_priority','policy_score','anomaly_percentile',
            'mandatory','evidence_gap','reasons','pending_transfer_count')})
    payload = {
        'schema': 'aegis-shadow-pilot-1.0',
        'frozen_utc':datetime.now(timezone.utc).isoformat(),
        'review_window_days':90,
        'model_schema_version':preview['model_schema_version'],
        'total_accounts':preview['total_accounts'],
        'parameters': {'review_budget_percent': budget,
                       'policy_threshold':policy, 'anomaly_threshold':anomaly},
        'records':records,
    }
    if path.exists() or manual_template.exists():
        raise FileExistsError('Create new immutable snapshot filenames for each pilot cycle')
    path.parent.mkdir(parents=True,exist_ok=True)
    manual_template.parent.mkdir(parents=True,exist_ok=True)
    digest=hash_payload(payload)
    envelope={'payload':payload,'sha256':digest}
    if os.getenv('AEGIS_PILOT_SIGNING_KEY'):
        envelope['hmac_sha256']=hmac.new(os.environ['AEGIS_PILOT_SIGNING_KEY'].encode(),
                              digest.encode(),hashlib.sha256).hexdigest()
    path.write_text(json.dumps(envelope,indent=2,default=str),encoding='utf-8')
    # Independent reviewers do not see ML ranking/predictions in their template.
    with manual_template.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['account_id','decision','review_minutes','severity','reviewer','reason'])
        w.writeheader()
        for item in records:
            w.writerow({'account_id':item['account_id']})
    return {'frozen':str(path),'manual_template':str(manual_template),
            'accounts':len(records),'sha256':envelope['sha256'],
            'note':'Keep frozen scores blind to full-manual reviewers.'}


def load_frozen(path):
    envelope=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(envelope,dict) or not isinstance(envelope.get('payload'),dict):
        raise ValueError('Invalid shadow-pilot artifact')
    digest=hash_payload(envelope['payload'])
    if not hmac.compare_digest(digest,str(envelope.get('sha256',''))):
        raise ValueError('Frozen artifact hash mismatch: manual editing is forbidden')
    key=os.getenv('AEGIS_PILOT_SIGNING_KEY')
    if os.getenv('AEGIS_REQUIRE_SIGNED_PILOTS','false').lower()=='true' and not key:
        raise ValueError('Pilot signing key required in protected mode')
    if key:
        expected=hmac.new(key.encode(),digest.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,str(envelope.get('hmac_sha256',''))):
            raise ValueError('Pilot artifact signature missing/invalid')
    payload=envelope['payload']
    if payload.get('schema')!='aegis-shadow-pilot-1.0':
        raise ValueError('Unsupported shadow-pilot schema')
    ids=[str(r['account_id']) for r in payload.get('records',[])]
    if not ids or len(ids)!=len(set(ids)):
        raise ValueError('Empty or duplicate frozen account IDs')
    return payload


def load_manual(path, expected_ids):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        manual=list(csv.DictReader(f))
    index={}
    for row in manual:
        key=str(row.get('account_id','')).strip()
        if not key or key in index:
            raise ValueError('Missing or duplicate manual account_id')
        if row.get('decision','').strip().lower() not in DECISIONS:
            raise ValueError('Full manual review must record retain/remove/followup for every account')
        if row.get('severity','').strip().lower() not in SEVERITIES:
            raise ValueError('Each manual review needs severity: critical/high/medium/low')
        if not row.get('reviewer','').strip():
            raise ValueError('Independent reviewer identity is required')
        if not row.get('reason','').strip():
            raise ValueError('Manual decision requires evidence/rationale')
        try:
            minutes=float(row.get('review_minutes',''))
        except (ValueError,TypeError):
            raise ValueError('Invalid manual review duration')
        if not 0<=minutes<=1440:
            raise ValueError('review_minutes must be 0..1440')
        index[key]={**row,'decision':row['decision'].strip().lower(),
                    'severity':row['severity'].strip().lower(),
                    'review_minutes':minutes}
    if set(index)!=set(expected_ids):
        raise ValueError('A pilot must include 100% full manual reviews (no missing or extra accounts)')
    return index


def wilson_upper(misses, positives, confidence_z=1.96):
    """Upper confidence limit for missed-case proportion, not a guarantee."""
    if positives<=0:
        return None
    p=misses/positives
    denom=1+confidence_z**2/positives
    center=(p+confidence_z**2/(2*positives))/denom
    half=confidence_z*sqrt(p*(1-p)/positives+confidence_z**2/(4*positives**2))/denom
    return round(min(1.0,center+half),4)


def selection(records, *, budget, policy, anomaly):
    if not 0<budget<=100 or not 0<=policy<=100 or not 0<anomaly<=1:
        raise ValueError('Invalid review capacity/policy/anomaly threshold')
    n=len(records)
    capacity=ceil(n*budget/100)
    mandatory=[r for r in records if bool(r['mandatory'])]
    candidates=[r for r in records if not r['mandatory'] and (
        int(r['policy_score'])>=policy or
        (r.get('anomaly_percentile') is not None and float(r['anomaly_percentile'])>=anomaly))]
    candidates.sort(key=lambda r:(-float(r['policy_score']),
                                  -float(r.get('anomaly_percentile') or 0),str(r['account_id'])))
    # Mandatory cases override the budget; a transfer cannot be thresholded out.
    return {str(r['account_id']) for r in mandatory+candidates[:max(0,capacity-len(mandatory))]}


def measure(frozen, manual, *, budget=None, policy=None, anomaly=None):
    params=frozen['parameters']
    budget=float(params['review_budget_percent'] if budget is None else budget)
    policy=int(params['policy_threshold'] if policy is None else policy)
    anomaly=float(params['anomaly_threshold'] if anomaly is None else anomaly)
    records=frozen['records']
    selected=selection(records,budget=budget,policy=policy,anomaly=anomaly)
    positives={key for key,v in manual.items() if v['decision'] in POSITIVE}
    misses=positives-selected
    selected_hits=positives&selected
    critical={key for key,v in manual.items() if v['decision'] in POSITIVE and v['severity']=='critical'}
    high={key for key,v in manual.items() if v['decision'] in POSITIVE and v['severity'] in ('critical','high')}
    all_minutes=sum(rec['review_minutes'] for rec in manual.values())
    selected_minutes=sum(manual[key]['review_minutes'] for key in selected)
    by_platform={}
    for platform in sorted(set(str(r['platform']) for r in records)):
        ids={str(r['account_id']) for r in records if r['platform']==platform}
        positives_in=ids&positives
        by_platform[platform]={
            'accounts':len(ids),'positive':len(positives_in),
            'selected':len(ids&selected),
            'missed':len(positives_in-selected),
            'recall':round(len(positives_in&selected)/len(positives_in),4) if positives_in else None}
    return {
        'accounts':len(records),'manual_positive':len(positives),
        'selected':len(selected),'mandatory':sum(bool(r['mandatory']) for r in records),
        'selection_rate':round(len(selected)/len(records),4),
        'true_positives':len(selected_hits),'false_negatives':len(misses),
        'false_positives':len(selected-positives),
        'false_negative_rate':round(len(misses)/len(positives),4) if positives else None,
        'recall':round(len(selected_hits)/len(positives),4) if positives else None,
        'precision':round(len(selected_hits)/len(selected),4) if selected else None,
        'missed_high_or_critical':len(high-selected),
        'missed_critical':len(critical-selected),
        'fnr_wilson_95pct_upper':wilson_upper(len(misses),len(positives)),
        'manual_total_minutes':round(all_minutes,2),
        'hypothetical_shortlist_minutes':round(selected_minutes,2),
        'hypothetical_minutes_outside_queue':round(all_minutes-selected_minutes,2),
        'parameters':{'review_budget_percent':budget,'policy_threshold':policy,'anomaly_threshold':anomaly},
        'by_platform':by_platform,
        'missed_account_ids_for_restricted_audit':sorted(misses),
        'safety_note':('Pilot requires 100% manual reviews; avoided minutes are hypothetical, not real saved time. '
                       'Missing a flagged account is NOT permission to keep it without the required review.'),
    }


def evaluate(frozen_path, manual_path, *, budget=None, policy=None, anomaly=None):
    frozen=load_frozen(frozen_path)
    manual=load_manual(manual_path,[str(r['account_id']) for r in frozen['records']])
    return measure(frozen,manual,budget=budget,policy=policy,anomaly=anomaly)


def calibrate(frozen_path,manual_path, *, budgets, policies, anomalies,
              max_missed_case_rate, max_critical_misses=0, max_high_misses=None):
    """Only ranks candidate parameters for pilot A. Does NOT deploy them.

    Acceptance limit is an explicit organization decision; never infer an
    acceptable missed-case rate from the data and never tune on validation B.
    """
    if max_missed_case_rate is None or not 0<=max_missed_case_rate<=1:
        raise ValueError('Obtain an explicit pilot missed-case tolerance (0..1) from the organization')
    frozen=load_frozen(frozen_path)
    manual=load_manual(manual_path,[str(r['account_id']) for r in frozen['records']])
    candidates=[]
    for budget,policy,anomaly in product(budgets,policies,anomalies):
        m=measure(frozen,manual,budget=float(budget),policy=int(policy),anomaly=float(anomaly))
        m.pop('missed_account_ids_for_restricted_audit')
        acceptable=(m['false_negative_rate'] is not None and
                    m['false_negative_rate']<=max_missed_case_rate and
                    m['missed_critical']<=max_critical_misses and
                    (max_high_misses is None or m['missed_high_or_critical']<=max_high_misses))
        m['passes_pilot_targets']=acceptable
        candidates.append(m)
    acceptable=[r for r in candidates if r['passes_pilot_targets']]
    acceptable.sort(key=lambda r:(r['selected'],r['false_negatives'],r['false_positives']))
    return {
        'calibration_only':True,
        'pilot_targets':{'max_missed_case_rate':max_missed_case_rate,
                         'max_critical_misses':max_critical_misses,
                         'max_high_misses':max_high_misses},
        'tested_parameter_sets':len(candidates),'acceptable_parameter_sets':len(acceptable),
        'recommended_for_independent_validation':acceptable[0] if acceptable else None,
        'status':'candidate_requires_untouched_pilot_B' if acceptable else 'no_setting_met_safety_targets',
        'important':('Run the selected parameters on a new untouched pilot B. '
                     'Never change production review exemptions automatically.'),
    }


def main():
    p=argparse.ArgumentParser(description='Aegis independent parallel-review pilot')
    sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze')
    f.add_argument('--frozen',type=Path,required=True)
    f.add_argument('--manual-template',type=Path,required=True)
    f.add_argument('--budget',type=float,default=10)
    f.add_argument('--policy',type=int,default=25)
    f.add_argument('--anomaly',type=float,default=.95)
    e=sub.add_parser('evaluate')
    e.add_argument('--frozen',type=Path,required=True)
    e.add_argument('--manual',type=Path,required=True)
    e.add_argument('--budget',type=float)
    e.add_argument('--policy',type=int)
    e.add_argument('--anomaly',type=float)
    c=sub.add_parser('calibrate')
    c.add_argument('--frozen',type=Path,required=True)
    c.add_argument('--manual',type=Path,required=True)
    c.add_argument('--max-missed-case-rate',type=float,required=True)
    c.add_argument('--budgets',default='10,20,30')
    c.add_argument('--policies',default='15,25,35')
    c.add_argument('--anomalies',default='.90,.95,.99')
    args=p.parse_args()
    if args.command=='freeze':
        output=freeze_to_file(args.frozen,args.manual_template,budget=args.budget,
                              policy=args.policy,anomaly=args.anomaly)
    elif args.command=='evaluate':
        output=evaluate(args.frozen,args.manual,budget=args.budget,
                        policy=args.policy,anomaly=args.anomaly)
    else:
        output=calibrate(args.frozen,args.manual,
             budgets=[float(x) for x in args.budgets.split(',')],
             policies=[int(x) for x in args.policies.split(',')],
             anomalies=[float(x) for x in args.anomalies.split(',')],
             max_missed_case_rate=args.max_missed_case_rate)
    print(json.dumps(output,indent=2,default=str))

if __name__=='__main__':
    main()
