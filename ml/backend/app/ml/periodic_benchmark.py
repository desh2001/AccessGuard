"""Demo-only top-K evaluation: hybrid policy + ML versus ML alone.
Group-based held-out, using synthetic labels. Not a real-company validation.
"""
from pathlib import Path
import argparse
import json
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from .periodic_model import load_periodic, predict_periodic
from .periodic_queue import make_review_queue


def benchmark(data, artifact, budget=10.0):
    _, indices = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=artifact['metadata']['seed']).split(data, data.label, data.group_id))
    held = data.iloc[indices].copy().reset_index(drop=True)
    rows = []
    for i,r in held.iterrows():
        row = r.to_dict()
        row.update(account_id=i+1, username=f'fictional-{i+1}', employee_code=None, period_days=90)
        rows.append(row)
    positives = int(held.label.sum())
    def calculate(result):
        selected = {r['account_id']-1 for r in result['accounts'] if r['review_priority'] in ('mandatory', 'selected')}
        hits = sum(int(held.iloc[i].label) for i in selected)
        return {'selected':len(selected), 'mandatory':result['mandatory_count'],
                'deferred_review_candidates':result['deferred_candidate_count'],
                'insufficient_evidence':result['insufficient_evidence_count'],
                'precision':round(hits/max(1,len(selected)),4),
                'recall':round(hits/positives,4) if positives else None,
                'missed_review_needed':positives-hits,
                'workload_reduction_fraction':round(1-len(selected)/len(rows),4)}
    rules = calculate(make_review_queue(rows, budget, None))
    hybrid = calculate(make_review_queue(rows, budget, artifact))
    return {
        'validation':'FICTIONAL SYNTHETIC SCENARIOS ONLY',
        'heldout_accounts':len(rows),'labeled_review_needed':positives,
        'requested_review_budget_percent':budget,
        'rule_only':rules,'hybrid_rule_plus_ml':hybrid,
        'recall_delta_hybrid_minus_rules':round(hybrid['recall']-rules['recall'],4)
              if hybrid['recall'] is not None and rules['recall'] is not None else None,
        'note':'Workload means selected review count, NOT measured hours. A queue cannot certify unselected accounts. Independent real reviews are required before claiming benefit.'
    }



def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--csv',type=Path,default=Path('ml_data/periodic_synthetic.csv'))
    ap.add_argument('--budget',type=float,default=10.0)
    args=ap.parse_args()
    artifact=load_periodic()
    if artifact is None:
        ap.error('Train the periodic model first')
    print(json.dumps(benchmark(pd.read_csv(args.csv),artifact,args.budget), indent=2))

if __name__=='__main__':
    from .platform_benchmark import main as platform_main
    platform_main()
