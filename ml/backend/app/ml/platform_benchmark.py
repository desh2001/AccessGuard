"""Synthetic/offline three-model review shortlist vs rules-only comparison.

Pilot outcomes: use the V6/V7 independent full-review or sampled pilot workflow.
This command is a *training pipeline smoke test* not a field-validation result.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from .platform_models import load_all_platforms, SUPPORTED_MODELS, platform_key
from .periodic_queue import make_review_queue


def benchmark(data: pd.DataFrame, models: dict, budget: float = 10, seed: int = 42):
    # Each trained model was fitted with a group-based 25% holdout at this seed.
    # Select that SAME held-out cohort for benchmarking; never use trained rows.
    frames = []
    for platform in SUPPORTED_MODELS:
        part = data.loc[data['platform'].map(platform_key) == platform].copy()
        _, test = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=seed).split(
            part, part['label'], part['group_id']))
        frames.append(part.iloc[test])
    held = pd.concat(frames, ignore_index=True)
    rows = []
    for i, r in held.iterrows():
        item = r.to_dict()
        item.update(account_id=i+1, username=f'synthetic-account-{i+1}', employee_code=None, period_days=90)
        rows.append(item)
    rules = make_review_queue(rows, budget)
    hybrid = make_review_queue(rows, budget, platform_models=models)
    label = held.label.astype(int).tolist()

    def score(queue):
        chosen = {r['account_id']-1 for r in queue['accounts'] if r['review_priority'] in ('mandatory','selected')}
        positives = sum(label)
        hits = sum(label[i] for i in chosen)
        return dict(selected=len(chosen), true_positives=hits, all_positives=positives,
                    missed_review_needed=positives-hits,
                    precision=round(hits/len(chosen),4) if chosen else None,
                    recall=round(hits/positives,4) if positives else None,
                    selected_fraction=round(len(chosen)/len(rows),4))
    return dict(validation='SYNTHETIC HELD-OUT DATA ONLY', total_holdout_accounts=len(rows),
                model_counts={p:int((held.platform.map(platform_key)==p).sum()) for p in SUPPORTED_MODELS},
                platform_ml_scored=hybrid['platform_model_scored'],
                rule_only=score(rules), hybrid=score(hybrid),
                note='A low selected_fraction is not evidence of safety or measured labor savings. Run manual-review pilot A and untouched B.')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--csv',type=Path,default=Path('ml_data/periodic_synthetic.csv'))
    ap.add_argument('--budget',type=float,default=10)
    ap.add_argument('--seed',type=int,default=42)
    args=ap.parse_args()
    models=load_all_platforms()
    missing=set(SUPPORTED_MODELS)-set(models)
    if missing:
        ap.error(f'Train missing models first: {sorted(missing)}')
    print(json.dumps(benchmark(pd.read_csv(args.csv), models, args.budget, args.seed),indent=2))

if __name__=='__main__':
    main()
