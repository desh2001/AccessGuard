"""Fit and score a reproducible anomaly baseline; never authorize revocation.

The model is trained only on human-confirmed normal cases (label=0) from the
training partition. Labels in the held-out partition are used only for evaluation.
Scoring reports empirical rarity, NOT the probability an access grant is unsafe.
"""
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import json
import os
import sys
import tempfile

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from .features import CATEGORICAL, NUMERIC, FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "ml_artifacts" / "access_anomaly_model.joblib"
MIN_NORMAL_TRAIN = 80


def model_path() -> Path:
    return Path(os.environ.get("ML_MODEL_PATH") or DEFAULT_PATH).resolve()


def normalized_frame(data: pd.DataFrame) -> pd.DataFrame:
    missing = set(FEATURE_COLUMNS) - set(data.columns)
    if missing:
        raise ValueError(f"Missing required feature columns: {sorted(missing)}")
    frame = data.loc[:, FEATURE_COLUMNS].copy()
    for column in CATEGORICAL:
        frame[column] = frame[column].fillna("Unknown").astype(str).str.strip().str.lower()
    for column in NUMERIC:
        frame[column] = pd.to_numeric(frame[column], errors="raise").fillna(0).clip(lower=0)
        if column.endswith("_days"):
            frame[column] = frame[column].clip(upper=365)
        else:
            if not frame[column].isin([0, 1]).all():
                raise ValueError(f"{column} must contain only 0 or 1")
    # No unobserved resource-use time can become a fabricated inactivity duration.
    frame.loc[frame["resource_use_observed"] == 0, "last_used_days"] = 0
    frame.loc[frame["last_login_observed"] == 0, "last_login_days"] = 0
    return frame


def build_pipeline(seed: int, n_estimators: int = 160) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("numeric", "passthrough", NUMERIC),
        ],
        remainder="drop",
    )
    return Pipeline([
        ("preprocessor", preprocessor),
        ("detector", IsolationForest(n_estimators=n_estimators, max_samples="auto",
                                      contamination="auto", random_state=seed, n_jobs=1)),
    ])


def anomaly_percentile(raw_scores: np.ndarray, reference_scores: np.ndarray) -> np.ndarray:
    """Higher percentile = rarer relative to confirmed-normal training cohort."""
    return np.searchsorted(reference_scores, raw_scores, side="right") / len(reference_scores)


def train_dataframe(data: pd.DataFrame, *, seed: int = 42, normal_quantile: float = 0.95,
                    n_estimators: int = 160) -> tuple[dict, dict]:
    required = {"label", "group_id"}
    if not required.issubset(data.columns):
        raise ValueError("Training CSV needs label (0 normal, 1 suspicious) and group_id")
    if len(data) < 150:
        raise ValueError("Need at least 150 examples (prefer representative, independently reviewed real cases)")
    labels = pd.to_numeric(data["label"], errors="raise")
    if labels.isna().any() or not labels.isin([0, 1]).all():
        raise ValueError("Labels must be 0 or 1, without missing values")
    if data["group_id"].isna().any() or (data["group_id"].astype(str).str.strip() == "").any():
        raise ValueError("group_id is required to prevent employee-level train/test leakage")
    if not (0.5 <= normal_quantile < 1):
        raise ValueError("normal_quantile must be in [0.5,1)")
    frame = normalized_frame(data)
    group_ids = data["group_id"].astype(str)
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.25,
                                                 random_state=seed).split(frame, labels, group_ids))
    X_train = frame.iloc[train_idx].loc[labels.iloc[train_idx] == 0]
    X_test = frame.iloc[test_idx]
    y_test = labels.iloc[test_idx].astype(int).to_numpy()
    if len(X_train) < MIN_NORMAL_TRAIN:
        raise ValueError(f"At least {MIN_NORMAL_TRAIN} reviewed-normal training rows are needed")
    if len(set(y_test)) != 2:
        raise ValueError("Held-out split needs both classes to compute evaluation metrics")
    pipeline = build_pipeline(seed, n_estimators=n_estimators)
    pipeline.fit(X_train)
    # score_samples: higher means more normal; negate so high = anomalous
    normal_scores = np.sort(-pipeline.score_samples(X_train))
    cutoff = float(np.quantile(normal_scores, normal_quantile))
    test_scores = -pipeline.score_samples(X_test)
    flagged = (test_scores > cutoff).astype(int)
    cm = confusion_matrix(y_test, flagged, labels=[0, 1]).tolist()
    metrics = {
        "precision": round(float(precision_score(y_test, flagged, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, flagged, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, flagged, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, test_scores)), 4),
        "average_precision": round(float(average_precision_score(y_test, test_scores)), 4),
        "confusion_matrix_tn_fp_fn_tp": [int(cm[0][0]), int(cm[0][1]), int(cm[1][0]), int(cm[1][1])],
        "heldout_positive_count": int(y_test.sum()),
        "heldout_negative_count": int(len(y_test) - y_test.sum()),
    }
    metadata = {
        "model": "IsolationForest", "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_columns": FEATURE_COLUMNS, "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0], "sklearn_version": sklearn.__version__,
        "training_normal_rows": len(X_train), "train_groups": int(group_ids.iloc[train_idx].nunique()),
        "heldout_rows": len(y_test), "heldout_groups": int(group_ids.iloc[test_idx].nunique()),
        "threshold_normal_quantile": normal_quantile, "raw_score_threshold": cutoff,
        "random_seed": seed, "number_of_trees": n_estimators,
        "evaluation": metrics,
        "disclaimer": "Anomaly percentile is not probability of risk. Metrics are only meaningful for the stated dataset and labels.",
    }
    return {"pipeline": pipeline, "normal_reference_scores": normal_scores,
            "threshold": cutoff, "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "metadata": metadata}, metadata


def save_artifact(artifact: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".joblib", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        joblib.dump(artifact, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    metadata_path = destination.with_suffix(".json")
    metadata_path.write_text(json.dumps(artifact["metadata"], indent=2) + "\n", encoding="utf-8")


@lru_cache(maxsize=4)
def _read_trusted_artifact(path: str, modified_ns: int, size: int) -> dict:
    # SECURITY: joblib uses pickle. Load ONLY locally generated trusted artifacts.
    artifact = joblib.load(path)
    if artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise ValueError("ML feature schema incompatible; retrain the model")
    if artifact["metadata"].get("sklearn_version") != sklearn.__version__:
        raise ValueError("scikit-learn version differs from training; retrain in this environment")
    return artifact


def load_model(path: Path | None = None) -> dict | None:
    path = path or model_path()
    if not path.is_file():
        return None
    stat = path.stat()
    return _read_trusted_artifact(str(path), stat.st_mtime_ns, stat.st_size)


def score_rows(rows: list[dict], artifact: dict) -> list[dict]:
    if not rows:
        return []
    frame = normalized_frame(pd.DataFrame(rows))
    raw = -artifact["pipeline"].score_samples(frame)
    percentile = anomaly_percentile(raw, artifact["normal_reference_scores"])
    return [{"anomaly_percentile": round(float(p), 4),
             "is_anomaly": bool(s > artifact["threshold"])}
            for s, p in zip(raw, percentile)]


def model_status() -> dict:
    path = model_path()
    if not path.exists():
        return {"ready": False, "state": "not_trained", "model": "IsolationForest",
                "note": "Rule-only scoring active. Train and deploy a trusted model to enable anomaly detection."}
    try:
        artifact = load_model(path)
        return {"ready": True, "state": "loaded", "model": "IsolationForest",
                "metadata": artifact["metadata"],
                "note": "Training/evaluation metadata; percentile is NOT a risk probability."}
    except (OSError, ValueError, KeyError, ImportError) as exc:
        return {"ready": False, "state": "invalid_model", "model": "IsolationForest",
                "note": f"Model cannot be loaded: {type(exc).__name__}. Retrain using trusted source data."}
