"""Honest held-out comparison: policy-only vs ML on scenario-generated labels.

Run after training: python -m app.ml.benchmark --csv ml_data/synthetic_demo.csv
The benchmark is synthetic and favors the rules from which many scenarios arose.
"""
import argparse
from pathlib import Path
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit
from .model import load_model, normalized_frame, score_rows


def policy_score(frame: pd.DataFrame) -> pd.Series:
    """Mirror the rule component of app.risk.recompute for feature CSV data."""
    f = normalized_frame(frame)
    return (
        40*f["unmapped"] +
        45*((f["employee_status"] != "active") & (f["unmapped"] == 0)).astype(int) +
        20*(f["permission_class"] == "privileged").astype(int) +
        15*f["sensitivity"].isin(["high", "critical"]).astype(int) +
        25*f["outside_role"] +
        25*((f["resource_use_observed"] == 1) & (f["last_used_days"] >= 90)).astype(int) +
        10*((f["resource_use_observed"] == 1) & (f["last_used_days"].between(60, 89))).astype(int) +
        10*((f["last_login_observed"] == 1) & (f["last_login_days"] >= 90)).astype(int)
    ).clip(upper=100)


def compare(data: pd.DataFrame, artifact: dict) -> dict:
    seed = artifact["metadata"]["random_seed"]
    _, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.25,
                                         random_state=seed).split(data, data["label"], data["group_id"]))
    heldout = data.iloc[test_idx]
    actual = heldout["label"].astype(int)
    rule_scores = policy_score(heldout)
    ml_flags = [int(p["is_anomaly"]) for p in score_rows(heldout.to_dict(orient="records"), artifact)]
    results = {}
    for method, predicted in [
        ("policy_medium_or_higher", (rule_scores >= 35).astype(int)),
        ("policy_high_only", (rule_scores >= 70).astype(int)),
        ("isolation_forest", ml_flags),
    ]:
        cm = confusion_matrix(actual, predicted, labels=[0,1]).flatten()
        results[method] = {
            "precision": round(float(precision_score(actual, predicted, zero_division=0)),4),
            "recall": round(float(recall_score(actual, predicted, zero_division=0)),4),
            "f1": round(float(f1_score(actual, predicted, zero_division=0)),4),
            "tn_fp_fn_tp": [int(n) for n in cm],
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    artifact = load_model()
    if artifact is None:
        parser.error("No trained model. Run python -m app.ml.train --csv ... first.")
    results = compare(pd.read_csv(args.csv), artifact)
    print("SYNTHETIC holdout (policy-created scenarios; NOT independent operational labels):")
    for name, v in results.items():
        print(f"{name:24} precision={v['precision']:.4f} recall={v['recall']:.4f} "
              f"f1={v['f1']:.4f} [TN,FP,FN,TP]={v['tn_fp_fn_tp']}")


if __name__ == "__main__":
    main()
