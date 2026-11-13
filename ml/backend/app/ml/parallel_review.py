"""Shadow (parallel) run: freeze ML selection BEFORE independent full manual review.

Manual file: account_id,decision,review_minutes; decision = retain/remove/followup.
'Positive' means manual reviewer wanted removal or follow-up, not actual malice.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from app.db import SessionLocal
from .periodic_queue import periodic_preview

VALID = {'retain', 'remove', 'followup'}


def freeze(path, *, budget, policy_threshold, anomaly_threshold):
    with SessionLocal() as db:
        result = periodic_preview(db, review_budget_percent=budget,
                                  policy_threshold=policy_threshold,
                                  anomaly_threshold=anomaly_threshold)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['account_id','review_priority','policy_score','anomaly_percentile'])
        writer.writeheader()
        for row in result['accounts']:
            writer.writerow({col: row.get(col) for col in writer.fieldnames})
    return {'frozen_account_count': len(result['accounts']), 'selected_count': result['selected_count'],
            'policy_threshold':policy_threshold, 'anomaly_threshold':anomaly_threshold,
            'budget':budget, 'frozen_predictions':str(path)}


def compare(predictions, manual):
    def read_records(path):
        with Path(path).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    pred_rows, labels = read_records(predictions), read_records(manual)
    if not pred_rows:
        raise ValueError('No frozen predictions')
    def index_by_id(rows):
        indexed = {}
        for row in rows:
            key = str(row.get('account_id', '')).strip()
            if not key or key in indexed:
                raise ValueError('Missing or duplicate account_id in shadow comparison')
            indexed[key] = row
        return indexed
    pred, full = index_by_id(pred_rows), index_by_id(labels)
    if set(pred) != set(full):
        raise ValueError('Parallel comparison requires independent manual decisions for ALL frozen accounts')
    for record in full.values():
        if record.get('decision', '').strip().lower() not in VALID:
            raise ValueError('Allowed manual decisions: retain, remove, followup')
        try:
            minutes = float(record.get('review_minutes', ''))
        except (TypeError, ValueError):
            raise ValueError('review_minutes must be a nonnegative number')
        if not 0 <= minutes <= 1440:
            raise ValueError('review_minutes must be 0..1440')
    selected = {k for k, v in pred.items() if v.get('review_priority') in ('mandatory', 'selected')}
    needs_review = {k for k, v in full.items() if v['decision'].strip().lower() in ('remove', 'followup')}
    hits = len(selected & needs_review)
    minutes_total = sum(float(v['review_minutes']) for v in full.values())
    minutes_selected = sum(float(full[k]['review_minutes']) for k in selected)
    return {
        'population':len(pred), 'manual_reviewed':len(full), 'manual_positive':len(needs_review),
        'model_selected':len(selected), 'true_positives':hits,
        'false_negatives':len(needs_review-selected),
        'false_positives':len(selected-needs_review),
        'recall_at_review_budget':round(hits/len(needs_review),4) if needs_review else None,
        'precision_at_review_budget':round(hits/len(selected),4) if selected else None,
        'manual_total_minutes':round(minutes_total,2),
        'manual_minutes_for_selected_accounts':round(minutes_selected,2),
        'potential_minutes_outside_selected_queue':round(minutes_total-minutes_selected,2),
        'caution':('Potential minutes is NOT verified savings: full manual review is still needed during parallel validation. '
                   'Evaluate a later untouched cycle before changing production review requirements.'),
    }


def main():
    parser=argparse.ArgumentParser(description='Parallel ML vs full manual review evaluation')
    sub=parser.add_subparsers(dest='command', required=True)
    fr=sub.add_parser('freeze')
    fr.add_argument('--out', type=Path, required=True)
    fr.add_argument('--budget', type=float, default=10)
    fr.add_argument('--policy', type=int, default=25)
    fr.add_argument('--anomaly', type=float, default=.95)
    cmp=sub.add_parser('compare')
    cmp.add_argument('--predictions', type=Path, required=True)
    cmp.add_argument('--manual', type=Path, required=True)
    args=parser.parse_args()
    if args.command=='freeze':
        print(json.dumps(freeze(args.out, budget=args.budget,
                                policy_threshold=args.policy, anomaly_threshold=args.anomaly),indent=2))
    else:
        print(json.dumps(compare(args.predictions, args.manual),indent=2))

if __name__=='__main__':
    main()
