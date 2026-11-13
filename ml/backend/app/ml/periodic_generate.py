"""Fully synthetic quarterly training data. Do not report as real-world performance."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from .periodic_features import FEATURE_COLUMNS


def generate(n=1600, seed=42):
    rng = np.random.default_rng(seed)
    departments = ['Finance','Engineering','HR','IT','Sales']
    platforms = ['Linux','Windows AD','GitHub']
    rows = []
    for i in range(n):
        dept = rng.choice(departments)
        plat = rng.choice(platforms)
        label = int(rng.random() < .20)
        scenario = rng.choice(['resigned','orphaned','stale','privileged_mismatch','unknown','usage_drop','employee_transfer','group_membership_change']) if label else 'routine'
        privileged = int(rng.random()<(.60 if label else .09))
        coverage = int(rng.choice([0,30,70,90],p=[.05,.05,.08,.82]))
        known = int(coverage>0)
        usage_events = int(rng.poisson(22)) if not label or scenario == 'privileged_mismatch' else int(rng.poisson(1))
        if scenario == 'stale': usage_events=0
        if scenario == 'usage_drop': usage_events=int(rng.poisson(35))
        if scenario == 'usage_drop':
            # High historical usage but almost no verified use in recent month.
            monthly = [int(usage_events*.6), int(usage_events*.4), 0]
            usage_events = sum(monthly)
        else:
            monthly = list(rng.multinomial(usage_events, [0.33, 0.33, 0.34]))
        observed = int(usage_events > 0 or rng.random()<.05)
        age = (int(rng.integers(31,61)) if scenario == 'usage_drop'
               else int(rng.integers(0,18)) if usage_events>0
               else (int(rng.integers(90,92)) if observed else 0))
        # AD fields are simulated from explicit snapshots/events, not inferred from log text.
        has_ad = bool(rng.random() < .85)
        transfer_n = int(scenario == 'employee_transfer')
        group_change_n = int(scenario == 'group_membership_change')
        group_count = int(rng.integers(1, 13)) if has_ad else 0
        row = {
            'group_id':f'demo-account-{i}', 'label':label, 'scenario':scenario,
            'platform':plat, 'department':dept, 'account_type':'human',
            'permission_profile':'privileged' if privileged else 'standard',
            'entitlement_count':int(rng.integers(1,8)),
            'privileged_entitlements':privileged,
            'sensitive_entitlements':int(privileged or rng.random()<.15),
            'outside_role_count':int(scenario=='privileged_mismatch'),
            'successful_logins_window':int(rng.poisson(18 if usage_events>0 else 1)),
            'failed_logins_window':int(rng.poisson(2)),
            'resource_use_events_window':usage_events,
            'active_days_window':int(min(90, max(usage_events, 0))),
            'distinct_resources_used_window':int(min(6, usage_events)),
            'permission_changes_window':int(rng.poisson(.3)),
            'use_age_days':age, 'use_evidence_observed':observed,
            'resource_uses_month_1':monthly[0],
            'resource_uses_month_2':monthly[1],
            'resource_uses_month_3':monthly[2],
            'log_coverage_days':coverage,
            'log_coverage_known':known,
            'ad_group_count':group_count,
            'privileged_ad_group_count':int(privileged and has_ad and rng.random() < .3),
            'ad_group_data_known':int(has_ad),
            'group_changes_window':group_change_n,
            'transfers_window':transfer_n,
            'manager_changes_window':transfer_n,
            'department_changes_window':transfer_n,
            'org_unit_changes_window':transfer_n,
            'recent_transfer_flag':transfer_n,
            'days_since_last_transfer':int(rng.integers(1,80)) if transfer_n else 0,
            'transfer_history_known':int(has_ad and rng.random() < .75),
            'ad_department_mismatch':int(scenario == 'employee_transfer' and rng.random() < .25),
            'ad_reporting_known':int(has_ad),
            'mapped_access_ad_group_count': int(group_count * .7) if has_ad else 0,
            'non_access_ad_group_count': int(group_count * .2) if has_ad else 0,
            'unmapped_ad_group_count': int(group_count * .1) if has_ad else 0,
            'out_of_scope_ad_group_count': int(scenario == 'employee_transfer'),
            'group_catalog_coverage_fraction': (.9 if has_ad else 0.0),
            'pending_transfer_count': transfer_n,
            # Optional source-specific *observational* signals. These are NOT proof
            # that a permission was exercised or that an event was a violation.
            'windows_privileged_logon_events': (int(rng.poisson(2)) if plat == 'Windows AD' and privileged else 0),
            'windows_privileged_logon_coverage_known': int(plat == 'Windows AD' and rng.random() < .80),
            'linux_sudo_events': (int(rng.poisson(3)) if plat == 'Linux' and privileged else 0),
            'linux_sudo_coverage_known': int(plat == 'Linux' and rng.random() < .80),
            'github_repo_activity_events': (int(rng.poisson(12)) if plat == 'GitHub' and usage_events else 0),
            'github_repo_activity_coverage_known': int(plat == 'GitHub' and rng.random() < .80),
        }
        if scenario == 'privileged_mismatch':
            row['permission_profile']='privileged'; row['privileged_entitlements']=1
            row['permission_changes_window']=int(rng.integers(3,8))
        if scenario == 'unknown':
            row['log_coverage_known']=0; row['log_coverage_days']=0
        row['employee_status'] = ('inactive' if scenario=='resigned' else 'unmapped' if scenario=='orphaned' else 'active')
        rows.append(row)
    source_signals = ['windows_privileged_logon_events', 'windows_privileged_logon_coverage_known',
                      'linux_sudo_events', 'linux_sudo_coverage_known',
                      'github_repo_activity_events', 'github_repo_activity_coverage_known']
    return pd.DataFrame(rows)[['group_id','label','scenario','employee_status'] + FEATURE_COLUMNS + source_signals]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=Path('ml_data/periodic_synthetic.csv'))
    ap.add_argument('--rows', type=int, default=1600)
    args=ap.parse_args()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    generate(args.rows).to_csv(args.out,index=False)
    print(f'Generated {args.rows} fictional account-cycle records: {args.out}')

if __name__=='__main__':main()
