"""Sampled, BLIND pilot of a full-population ML run.

Production workflow is ML over all accounts, human review of mandatory and
selected accounts, plus required independent quality sampling. During an
initial validation pilot, full manual review of a representative controlled
cohort is best; if impossible, randomized stratified independent manual
sampling can ESTIMATE missed cases. Reviewing ONLY model-selected accounts
cannot measure missed cases (verification bias).
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import random
from pathlib import Path
from .enterprise_pilot import selection, POSITIVE


def freeze_blind_sample(frozen, *, selected_sample, unselected_sample, seed):
    """Do not share stratum membership or model outputs with manual reviewers."""
    rows=frozen['records']
    ids=[str(r['account_id']) for r in rows]
    if len(ids)!=len(set(ids)) or not ids:
        raise ValueError('Frozen ML population must have unique nonempty account IDs')
    params=frozen['parameters']
    picked=selection(rows,budget=float(params['review_budget_percent']),
                     policy=int(params['policy_threshold']),anomaly=float(params['anomaly_threshold']))
    selected=sorted(picked)
    unselected=sorted(set(ids)-picked)
    if not selected or not unselected:
        raise ValueError('Need both selected and unselected strata to evaluate missed cases')
    if not (1<=selected_sample<=len(selected) and 1<=unselected_sample<=len(unselected)):
        raise ValueError('Sample both groups; sizes must fit their populations')
    rng=random.Random(seed)  # reproducible AFTER a model snapshot is frozen
    yes=rng.sample(selected,selected_sample)
    no=rng.sample(unselected,unselected_sample)
    rows_for_review = yes+no
    rng.shuffle(rows_for_review)
    return {
        'schema':'aegis-sampled-pilot-1',
        'created_at':datetime.now(timezone.utc).isoformat(),
        'population_sha256':hashlib.sha256(json.dumps(frozen,sort_keys=True,default=str).encode()).hexdigest(),
        'selected_population':len(selected), 'unselected_population':len(unselected),
        'selected_sample':selected_sample, 'unselected_sample':unselected_sample,
        'sampled_ids':rows_for_review,
        # Private, NEVER included in reviewer template.
        'private_stratum':{uid:('selected' if uid in picked else 'unselected') for uid in rows_for_review},
        'interpretation':'Stratified estimates are not exact population missed-case counts.'
    }


def write_blind_template(sample, path):
    """No ranks, reasons, selected status or scores in this CSV."""
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['account_id','decision','severity','review_minutes','reviewer','reason'])
        w.writeheader()
        for uid in sample['sampled_ids']:
            w.writerow({'account_id':uid})


def evaluate_sample(sample, completed_manual:dict):
    """Horvitz-Thompson-style simple stratum expansion; exploratory only.

    Manual labels must be from blinded reviewers; only complete sampled labels
    qualify. Do not use these point estimates to approve threshold deployment.
    """
    expected=set(sample['sampled_ids'])
    if set(completed_manual)!=expected:
        raise ValueError('All and only sampled account decisions must be present')
    for account_id,item in completed_manual.items():
        if item.get('decision') not in {'retain','remove','followup'}:
            raise ValueError('Invalid manual decision')
        if not item.get('reviewer') or not item.get('reason'):
            raise ValueError('Need blinded reviewer identity and reason')
        if not isinstance(item.get('review_minutes'),(int,float)) or item['review_minutes']<0:
            raise ValueError('Invalid timed review minutes')
    yes_weight=sample['selected_population']/sample['selected_sample']
    no_weight=sample['unselected_population']/sample['unselected_sample']
    yes_hits=sum(completed_manual[uid]['decision'] in POSITIVE for uid in expected
                 if sample['private_stratum'][uid]=='selected')
    no_hits=sum(completed_manual[uid]['decision'] in POSITIVE for uid in expected
                if sample['private_stratum'][uid]=='unselected')
    positive_selected_est=yes_hits*yes_weight
    missed_est=no_hits*no_weight
    denominator=positive_selected_est+missed_est
    observed_minutes=sum(v['review_minutes'] for v in completed_manual.values())
    return {
        'accounts_in_ml_population':sample['selected_population']+sample['unselected_population'],
        'independently_reviewed_sample':len(expected),
        'selected_sample_review_needed':yes_hits,
        'unselected_sample_review_needed':no_hits,
        'estimated_population_review_needed':round(denominator,2),
        'estimated_missed_cases':round(missed_est,2),
        'estimated_recall':round(positive_selected_est/denominator,4) if denominator else None,
        'estimated_missed_case_rate':round(missed_est/denominator,4) if denominator else None,
        'timed_sample_review_minutes':round(observed_minutes,2),
        'warning':('Estimates from stratified sampling, not exact missed cases. '
                   'Confidence intervals, adequate sample size, pilot B, and '
                   'organization-supplied missed-case tolerance are required. '
                   'Never calculate miss rate by reviewing only model-selected accounts.'),
        'automatic_promotion':False,
    }


def reconcile_completed_manual_reviews(frozen, manual_reviews, *, cycle_key):
    """Deduplicate REVIEW WORK, not employee accounts or authorized permissions.

    A manual decision counts as completed only if it is verified, in the same
    cycle and has human attestation. Mandatory transfer reviews need explicit
    transfer coverage evidence before removal from the outstanding review queue.
    No database writes or automatic revocation occur here.
    """
    rows=frozen['records']
    params=frozen['parameters']
    chosen=selection(rows,budget=float(params['review_budget_percent']),
                     policy=int(params['policy_threshold']),anomaly=float(params['anomaly_threshold']))
    index={str(r['account_id']):r for r in rows}
    if len(index)!=len(rows):
        raise ValueError('Duplicate ML account IDs')
    pending=[]; covered=[]
    for uid in sorted(chosen):
        item=manual_reviews.get(uid,{})
        valid=(item.get('cycle_key')==cycle_key and
               item.get('verified') is True and
               item.get('decision') in ('retain','remove','followup') and
               bool(item.get('reviewer')) and bool(item.get('rationale')))
        # Transfer-specific approval is a separate obligation, not just a
        # statement that one account was reviewed before a new transfer.
        if valid and index[uid].get('mandatory'):
            valid=bool(item.get('mandatory_obligations_covered'))
        if valid:
            covered.append(uid)
        else:
            pending.append(uid)
    return {'ml_selected':len(chosen),'already_reviewed_and_attested':covered,
            'still_to_review':pending,
            'note':'Never delete accounts or clear mandatory transfers from this output.'}
