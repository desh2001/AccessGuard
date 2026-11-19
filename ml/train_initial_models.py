"""Script to generate realistic baseline synthetic cohort and train the initial 3 platform models.

Generates:
- Windows AD model (ml/backend/ml_artifacts/platforms/windows.joblib)
- Linux Server model (ml/backend/ml_artifacts/platforms/linux.joblib)
- GitHub SaaS model (ml/backend/ml_artifacts/platforms/github.joblib)
"""
import sys
from pathlib import Path
import random
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.ml.platform_models import train_all_platforms, save_platform, platform_path


def generate_synthetic_data(samples_per_platform: int = 200, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    np.random.seed(seed)

    departments = ["IT", "Engineering", "Finance", "HR", "Operations", "Sales", "Legal"]
    account_types = [
        "human", "human", "human", "human",
        "service", "service",
        "workload", "vendor",
        "shared", "emergency",
        "machine", "unknown"
    ]
    profiles = ["standard", "standard", "standard", "elevated", "admin"]

    rows = []

    for platform in ["windows", "linux", "github"]:
        for i in range(samples_per_platform):
            # 85% normal baseline (label=0), 15% held-out anomalies (label=1)
            is_anomaly = (i >= int(samples_per_platform * 0.85))
            label = 1 if is_anomaly else 0

            dept = random.choice(departments)
            acct_type = random.choice(account_types)
            profile = random.choice(profiles)

            # Baseline vs anomaly distributions
            if not is_anomaly:
                active_days = random.randint(15, 65)
                logins = random.randint(20, 120)
                failed_logins = random.randint(0, 3)
                resource_uses = random.randint(10, 80)
                distinct_res = random.randint(2, 8)
                entitlements = random.randint(1, 8)
                priv_ent = 1 if profile == "admin" else 0
                sens_ent = 1 if profile in ("admin", "elevated") else 0
                m1 = resource_uses // 3
                m2 = resource_uses // 3
                m3 = resource_uses - m1 - m2
                use_age = random.randint(0, 5)
                use_obs = 1
                perm_changes = random.choice([0, 0, 0, 1])
                grp_changes = random.choice([0, 0, 0, 1])
                transfers = 0
                recent_xfer = 0
                out_scope_ad = 0
            else:
                # Anomalous: abrupt activity spike, weird dormancy, or excessive admin
                active_days = random.choice([1, 2, 75, 88])
                logins = random.choice([0, 1, 350, 500])
                failed_logins = random.choice([0, 15, 45])
                resource_uses = random.choice([0, 300, 600])
                distinct_res = random.choice([1, 25, 40])
                entitlements = random.randint(10, 30)
                priv_ent = random.randint(3, 8)
                sens_ent = random.randint(5, 12)
                m1 = 0
                m2 = 0
                m3 = resource_uses
                use_age = random.choice([45, 85, 0])
                use_obs = 1 if resource_uses > 0 else 0
                perm_changes = random.randint(2, 6)
                grp_changes = random.randint(2, 5)
                transfers = random.choice([0, 1])
                recent_xfer = transfers
                out_scope_ad = random.choice([0, 2, 4])

            row = {
                "platform": platform,
                "group_id": f"{platform}-acct-{i:04d}",
                "label": label,
                "account_type": acct_type,
                "permission_profile": profile,
                "department": dept,
                "entitlement_count": entitlements,
                "privileged_entitlements": priv_ent,
                "sensitive_entitlements": sens_ent,
                "successful_logins_window": logins,
                "failed_logins_window": failed_logins,
                "resource_use_events_window": resource_uses,
                "active_days_window": active_days,
                "distinct_resources_used_window": distinct_res,
                "permission_changes_window": perm_changes,
                "use_age_days": use_age,
                "use_evidence_observed": use_obs,
                "resource_uses_month_1": m1,
                "resource_uses_month_2": m2,
                "resource_uses_month_3": m3,
                "log_coverage_days": 90.0,
                "log_coverage_known": 1,
                "group_changes_window": grp_changes,
                "transfers_window": transfers,
                "recent_transfer_flag": recent_xfer,
                "out_of_scope_ad_group_count": out_scope_ad,
                "ad_group_data_known": 1,
                "privileged_ad_group_count": priv_ent,
            }

            if platform == "windows":
                row.update({
                    "ad_group_count": random.randint(2, 10),
                    "mapped_access_ad_group_count": random.randint(2, 8),
                    "unmapped_ad_group_count": 0,
                    "group_catalog_coverage_fraction": 1.0,
                    "manager_changes_window": 0,
                    "department_changes_window": transfers,
                    "ad_department_mismatch": 0,
                    "windows_privileged_logon_events": priv_ent * logins // 4,
                    "windows_privileged_logon_coverage_known": 1,
                })
            elif platform == "linux":
                row.update({
                    "linux_sudo_events": random.randint(0, 30) if profile in ("admin", "elevated") else 0,
                    "linux_sudo_coverage_known": 1,
                })
            elif platform == "github":
                row.update({
                    "github_repo_activity_events": resource_uses,
                    "github_repo_activity_coverage_known": 1,
                    "unmapped_ad_group_count": 0,
                })

            rows.append(row)

    return pd.DataFrame(rows)


def main():
    print("Generating synthetic cohort data (200 records per platform)...")
    df = generate_synthetic_data(samples_per_platform=200, seed=42)
    print(f"Total rows: {len(df)}")

    # Save to ml_data
    ml_data_dir = Path(__file__).resolve().parent / "backend" / "ml_data"
    ml_data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = ml_data_dir / "periodic_synthetic.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved dataset to {csv_path}")

    print("Training 3 independent platform models (Windows, Linux, GitHub)...")
    artifacts = train_all_platforms(df, seed=42, n_estimators=160)

    for platform_key, artifact in artifacts.items():
        saved_path = save_platform(artifact)
        eval_metrics = artifact["metadata"]["evaluation"]
        print(f"\n[OK] Trained {platform_key.upper()} Model:")
        print(f"  Artifact: {saved_path}")
        print(f"  Holdout Count: {eval_metrics['holdout_count']}")
        print(f"  Holdout Positives: {eval_metrics['holdout_positive']}")
        if "roc_auc" in eval_metrics:
            print(f"  ROC AUC: {eval_metrics['roc_auc']:.4f}")
        if "average_precision" in eval_metrics:
            print(f"  PR AUC: {eval_metrics['average_precision']:.4f}")

    print("\nAll 3 platform model artifacts trained and persisted successfully!")


if __name__ == "__main__":
    main()
