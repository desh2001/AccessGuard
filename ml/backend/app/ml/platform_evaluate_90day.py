"""Evaluate the frozen platform models against a separate 90-day ground-truth file.

The ground-truth table is merged ONLY for evaluation. It is never passed into
prepare_platform() or any scoring feature matrix.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .platform_models import SUPPORTED_MODELS, load_all_platforms, platform_key, predict_platform


def evaluate(features_path: Path, ground_truth_path: Path, budgets=(5, 10, 20)) -> dict:
    features = pd.read_csv(features_path)
    truth = pd.read_csv(ground_truth_path)
    required_truth = {"account_id", "ml_eval_eligible", "ml_eval_label"}
    if not required_truth.issubset(truth.columns):
        raise ValueError(f"Ground truth is missing columns: {sorted(required_truth - set(truth.columns))}")
    if features["account_id"].duplicated().any() or truth["account_id"].duplicated().any():
        raise ValueError("account_id must be unique in both 90-day files")
    joined = features.merge(
        truth[["account_id", "ml_eval_eligible", "ml_eval_label"]],
        on="account_id", how="inner", validate="one_to_one",
    )
    if len(joined) != len(features):
        raise ValueError("Feature rows and truth rows do not have a complete one-to-one account_id match")
    eligible_truth = joined.loc[joined["ml_eval_eligible"].astype(int) == 1, "ml_eval_label"]
    if eligible_truth.isna().any() or not eligible_truth.isin((0, 1)).all():
        raise ValueError("Eligible ml_eval_label values must contain only 0 or 1")

    models = load_all_platforms()
    missing = set(SUPPORTED_MODELS) - set(models)
    if missing:
        raise RuntimeError(f"Missing trained model artifacts: {sorted(missing)}")

    report = {
        "evaluation": "SEPARATE SYNTHETIC 90-DAY HOLDOUT; NOT ENTERPRISE VALIDATION",
        "feature_rows": len(features),
        "ground_truth_rows": len(truth),
        "eligible_rows": int((joined.ml_eval_eligible == 1).sum()),
        "models": {},
        "note": "Ground-truth labels are joined only after inference and are never features.",
    }
    for platform in SUPPORTED_MODELS:
        part = joined.loc[
            (joined["platform"].map(platform_key) == platform)
            & (joined["ml_eval_eligible"].astype(int) == 1)
        ].copy()
        if part.empty:
            report["models"][platform] = {"eligible": 0, "status": "no_eligible_rows"}
            continue
        # The API also enforces this coverage gate before inference.
        coverage_ok = (
            part["log_coverage_known"].astype(int).eq(1)
            & part["log_coverage_days"].astype(float).ge(89.55)
        )
        part = part.loc[coverage_ok]
        if part.empty:
            report["models"][platform] = {"eligible": 0, "status": "no_rows_with_sufficient_coverage"}
            continue
        rows = part.to_dict(orient="records")
        scores = predict_platform(rows, models[platform])
        labels = part["ml_eval_label"].astype(int).to_numpy()
        score_series = pd.Series(scores, index=part.index)
        result = {
            "status": "evaluated",
            "eligible_accounts": int(len(part)),
            "positive_cases": int(labels.sum()),
            "negative_cases": int(len(labels) - labels.sum()),
        }
        if len(set(labels.tolist())) == 2:
            result["roc_auc"] = round(float(roc_auc_score(labels, scores)), 4)
            result["average_precision"] = round(float(average_precision_score(labels, scores)), 4)
        else:
            result["roc_auc"] = None
            result["average_precision"] = None
            result["metric_note"] = "Both classes are required for ROC-AUC and average precision."
        for budget in budgets:
            count = max(1, int((len(part) * budget + 99.999) // 100))
            selected_indices = score_series.nlargest(count).index
            hits = int(part.loc[selected_indices, "ml_eval_label"].astype(int).sum())
            result[f"recall_at_{budget}_percent"] = round(hits / max(1, int(labels.sum())), 4)
            result[f"precision_at_{budget}_percent"] = round(hits / count, 4)
            result[f"selected_at_{budget}_percent"] = count
        report["models"][platform] = result
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    result = evaluate(args.features, args.ground_truth)
    output = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
