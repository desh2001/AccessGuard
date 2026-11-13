"""Read-only quarterly ML input monitoring, not automated retraining.

Compares present aggregate features to a trusted training/baseline CSV; no
employee identifiers, raw logs or account names enter numeric comparison.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .periodic_model import prepare_frame
from .periodic_features import NUMERIC, CATEGORICAL


def _population_stability(expected: np.ndarray, observed: np.ndarray, epsilon=1e-5):
    quantiles=np.unique(np.quantile(expected,np.linspace(0,1,11)))
    if len(quantiles)<3:
        return None  # No meaningful binning for constant or binary features
    bins=np.concatenate(([-np.inf],quantiles[1:-1],[np.inf]))
    exp=np.histogram(expected,bins=bins)[0]
    obs=np.histogram(observed,bins=bins)[0]
    p=np.clip(exp/max(len(expected),1),epsilon,1)
    q=np.clip(obs/max(len(observed),1),epsilon,1)
    p=p/p.sum(); q=q/q.sum()
    return float(np.sum((q-p)*np.log(q/p)))


def monitor(reference_rows, current_rows, *, psi_warning=0.25,
            unknown_group_warning=0.1, min_reference=100):
    """Return feature-drift and AD catalog-coverage report with policy knobs.

    PSI is descriptive only and can be misleading on sparse skewed data;
    investigate source changes and reviewed labels before retraining.
    """
    if not 0<psi_warning<10 or not 0<=unknown_group_warning<=1:
        raise ValueError('Invalid monitoring thresholds')
    baseline=prepare_frame(reference_rows)
    observed=prepare_frame(current_rows)
    if len(baseline)<min_reference or len(observed)<1:
        raise ValueError('Insufficient reference/current account feature rows')
    numeric={}
    for name in NUMERIC:
        x=baseline[name].to_numpy(dtype=float)
        y=observed[name].to_numpy(dtype=float)
        val=_population_stability(x,y)
        numeric[name]={'baseline_mean':round(float(x.mean()),4),
                       'current_mean':round(float(y.mean()),4),
                       'psi':round(val,4) if val is not None else None,
                       'drift_warning':val is not None and val>psi_warning}
    categorical={}
    for name in CATEGORICAL:
        old=baseline[name].value_counts(normalize=True)
        new=observed[name].value_counts(normalize=True)
        categorical[name]={'unseen_current_categories': sorted(set(new.index)-set(old.index)),
                           'baseline_categories':len(old),'current_categories':len(new)}
    current_groups=float(observed['ad_group_count'].sum())
    unknown_groups=float(observed['unmapped_ad_group_count'].sum())
    unknown_share=unknown_groups/current_groups if current_groups else None
    return {'baseline_accounts':len(baseline),'current_accounts':len(observed),
            'feature_schema':list(baseline.columns),
            'numeric':numeric,'categorical':categorical,
            'unmapped_ad_group_membership_share':round(unknown_share,4) if unknown_share is not None else None,
            'catalog_mapping_alert':unknown_share is not None and unknown_share>unknown_group_warning,
            'features_with_psi_warning':[name for name,values in numeric.items() if values['drift_warning']],
            'next_action':'Investigate data pipelines, mappings and peer changes; retrain only after explicit approval.'}


def main():
    p=argparse.ArgumentParser(description='Monitor quarterly feature drift without model writes')
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--current',type=Path,required=True)
    p.add_argument('--psi-warning',type=float,default=.25)
    p.add_argument('--unknown-group-warning',type=float,default=.10)
    args=p.parse_args()
    result=monitor(pd.read_csv(args.baseline),pd.read_csv(args.current),
                   psi_warning=args.psi_warning,unknown_group_warning=args.unknown_group_warning)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
