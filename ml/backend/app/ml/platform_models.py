"""Independent quarterly access-review models for Windows, Linux and GitHub.

Each source has its own trained pipeline, feature schema, normal reference
population, integrity-checked artifact and held-out evaluation. Raw events are
NOT fed to Isolation Forest; source adapters produce account-cycle features.
Unmapped platforms remain unscored, never silently mapped to another model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac
import json
import os
import tempfile

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

MODEL_SCHEMA_VERSION = "aegis-v8-quarterly-platform-specific-1"
SUPPORTED_MODELS = ("windows", "linux", "github")

# Stable, explicit platform aliases; GitLab is NOT treated as GitHub.
ALIASES = {
    "windows": "windows", "windows ad": "windows", "active directory": "windows",
    "windows server": "windows", "microsoft windows": "windows",
    "linux": "linux", "ubuntu": "linux", "rhel": "linux", "red hat linux": "linux",
    "debian": "linux", "centos": "linux",
    "github": "github", "github enterprise": "github", "github enterprise cloud": "github",
    "github enterprise server": "github",
}

# Source-specific configurations reside in independent adapter modules.
from .platforms import WINDOWS_CONFIG, LINUX_CONFIG, GITHUB_CONFIG
PLATFORM_CONFIG = {
    'windows': WINDOWS_CONFIG,
    'linux': LINUX_CONFIG,
    'github': GITHUB_CONFIG,
}


def platform_key(platform: str | None) -> str | None:
    return ALIASES.get(str(platform or "").strip().lower())


def platform_path(platform: str) -> Path:
    if platform not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported platform model: {platform}")
    base = Path(os.getenv("AEGIS_PLATFORM_MODEL_DIR", "")).expanduser() if os.getenv("AEGIS_PLATFORM_MODEL_DIR") else (
        Path(__file__).resolve().parents[2] / "ml_artifacts" / "platforms"
    )
    return (base / f"{platform}.joblib").resolve()


def prepare_platform(rows, platform: str) -> pd.DataFrame:
    """Strict schema per platform. Missing optional signals remain marked unknown."""
    config = PLATFORM_CONFIG[platform]
    frame = pd.DataFrame(rows)
    required = set(config["categorical"]) | (set(config["numeric"]) - {
        config["signal_count"], config["signal_known"]})
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required {platform} features: {sorted(missing)}")
    if "platform" not in frame.columns or any(platform_key(x) != platform for x in frame["platform"]):
        raise ValueError(f"Dataset contains a row not belonging to the {platform} model")
    for field in (config["signal_count"], config["signal_known"]):
        if field not in frame:
            frame[field] = 0
    names = list(config["categorical"]) + list(config["numeric"])
    frame = frame[names].copy()
    for col in config["categorical"]:
        frame[col] = frame[col].fillna("unknown").astype(str).str.strip().str.lower()
    for col in config["numeric"]:
        frame[col] = pd.to_numeric(frame[col], errors="raise").fillna(0)
        if not np.isfinite(frame[col].to_numpy()).all() or (frame[col] < 0).any():
            raise ValueError(f"Invalid numeric {platform} field: {col}")
    for flag in ("use_evidence_observed", "log_coverage_known", config["signal_known"]):
        if not frame[flag].isin((0, 1)).all():
            raise ValueError(f"{flag} must be 0 or 1")
    # Avoid interpreting absent signal feeds as zero events.
    frame.loc[frame[config["signal_known"]] == 0, config["signal_count"]] = 0
    frame.loc[frame["log_coverage_known"] == 0, "log_coverage_days"] = 0
    frame.loc[frame["use_evidence_observed"] == 0, "use_age_days"] = 0
    return frame


def train_platform(data: pd.DataFrame, platform: str, seed: int = 42,
                   n_estimators: int = 160) -> dict:
    if platform not in SUPPORTED_MODELS:
        raise ValueError("Unsupported model")
    if not 50 <= n_estimators <= 1000:
        raise ValueError("trees must be 50..1000")
    if not {"label", "group_id"}.issubset(data.columns):
        raise ValueError("Need independent label and group_id for honest held-out evaluation")
    if data["group_id"].isna().any():
        raise ValueError("group_id is required")
    if len(data) < 120:
        raise ValueError(f"Insufficient {platform} examples; need >=120")
    labels = pd.to_numeric(data["label"], errors="raise")
    if labels.isna().any() or not labels.isin([0, 1]).all():
        raise ValueError("label must be independently reviewed 0/1")
    frame = prepare_platform(data, platform)
    split = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    train_idx, test_idx = next(split.split(frame, labels, data["group_id"]))
    normal = frame.iloc[train_idx].loc[labels.iloc[train_idx] == 0]
    if len(normal) < 65:
        raise ValueError(f"Insufficient baseline normal {platform} records")
    config = PLATFORM_CONFIG[platform]
    transformer = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), list(config["categorical"])),
        ("numeric", StandardScaler(), list(config["numeric"])),
    ])
    pipe = Pipeline([
        ("preprocessor", transformer),
        ("detector", IsolationForest(n_estimators=n_estimators,
                                      contamination="auto", random_state=seed, n_jobs=1)),
    ])
    pipe.fit(normal)
    reference = np.sort(-pipe.score_samples(normal))
    # Account-type & department peer calibration where sample size is adequate.
    keys = (normal["account_type"].astype(str) + "|" + normal["department"].astype(str)).to_numpy()
    scores = -pipe.score_samples(normal)
    peers = {str(key): np.sort(scores[keys == key]) for key in np.unique(keys)
             if int((keys == key).sum()) >= 40}
    holdout = -pipe.score_samples(frame.iloc[test_idx])
    test_labels = labels.iloc[test_idx].to_numpy()
    metrics = {
        "holdout_count": int(len(test_idx)), "holdout_positive": int(test_labels.sum()),
        "holdout_unique_accounts": int(data.iloc[test_idx]["group_id"].nunique()),
        "eval_provenance": "Synthetic unless reviewed by independent owners",
    }
    if len(set(test_labels)) == 2:
        metrics.update(roc_auc=round(float(roc_auc_score(test_labels, holdout)), 4),
                       average_precision=round(float(average_precision_score(test_labels, holdout)), 4))
        for percentage in (5, 10, 20):
            count = max(1, int(np.ceil(len(holdout) * percentage / 100)))
            hits = int(test_labels[np.argsort(-holdout)[:count]].sum())
            metrics[f"recall_at_{percentage}_percent"] = round(hits / int(test_labels.sum()), 4)
            metrics[f"precision_at_{percentage}_percent"] = round(hits / count, 4)
    metadata = {
        "platform": platform, "schema": MODEL_SCHEMA_VERSION,
        "features": list(config["categorical"]) + list(config["numeric"]),
        "trained_utc": datetime.now(timezone.utc).isoformat(),
        "algorithm": "IsolationForest", "trees": n_estimators, "seed": seed,
        "normal_training_records": len(normal), "peer_reference_counts": {k: len(v) for k,v in peers.items()},
        "evaluation": metrics,
        "limitation": "Anomaly percentile != inappropriate access. Use review-policy rules and human decisions.",
    }
    return {"model_key": platform, "schema": MODEL_SCHEMA_VERSION, "pipeline": pipe,
            "reference": reference, "peer_references": peers, "metadata": metadata}


def train_all_platforms(data: pd.DataFrame, seed: int = 42,
                        n_estimators: int = 160) -> dict[str, dict]:
    if "platform" not in data:
        raise ValueError("Input must include platform field")
    out = {}
    for platform in SUPPORTED_MODELS:
        group = data.loc[data["platform"].map(platform_key) == platform].copy()
        out[platform] = train_platform(group, platform, seed=seed, n_estimators=n_estimators)
    return out


def _digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for buf in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(buf)
    return sha.hexdigest()


def save_platform(artifact: dict, destination: Path | None = None) -> Path:
    platform = artifact["model_key"]
    path = Path(destination or platform_path(platform))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".joblib", delete=False) as handle:
        temp = Path(handle.name)
    try:
        joblib.dump(artifact, temp)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    digest = _digest(path)
    manifest = {**artifact["metadata"], "sha256": digest}
    key = os.getenv("AEGIS_MODEL_SIGNING_KEY")
    if key:
        manifest["hmac_sha256"] = hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest()
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     suffix=".json", delete=False) as handle:
        temp_manifest = Path(handle.name)
        json.dump(manifest, handle, indent=2)
    temp_manifest.replace(path.with_suffix(".json"))
    return path


def load_platform(platform: str, path: Path | None = None) -> dict | None:
    if platform not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown platform model: {platform}")
    path = Path(path or platform_path(platform))
    if not path.exists():
        return None
    manifest_path = path.with_suffix(".json")
    if not manifest_path.exists():
        raise ValueError(f"Missing {platform} model manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = _digest(path)
    if not hmac.compare_digest(str(manifest.get("sha256", "")), digest):
        raise ValueError(f"Tampered {platform} model artifact")
    key = os.getenv("AEGIS_MODEL_SIGNING_KEY")
    required = os.getenv("AEGIS_REQUIRE_SIGNED_MODELS", "false").lower() == "true"
    if required and not key:
        raise ValueError("AEGIS_MODEL_SIGNING_KEY required when signatures are enforced")
    if key:
        expected = hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(manifest.get("hmac_sha256", "")), expected):
            raise ValueError(f"Model HMAC mismatch: {platform}")
    # joblib uses pickle: load ONLY from access-controlled, trusted artifact storage.
    artifact = joblib.load(path)
    if (artifact.get("model_key") != platform or artifact.get("schema") != MODEL_SCHEMA_VERSION
        or manifest.get("platform") != platform or manifest.get("schema") != MODEL_SCHEMA_VERSION
        or artifact.get("metadata", {}).get("features") != manifest.get("features")):
        raise ValueError(f"Wrong platform or incompatible schema in {platform} model")
    return artifact


def load_all_platforms() -> dict[str, dict]:
    return {key: model for key in SUPPORTED_MODELS
            if (model := load_platform(key)) is not None}


def predict_platform(rows: list[dict], artifact: dict) -> list[float]:
    if not rows:
        return []
    platform = artifact["model_key"]
    frame = prepare_platform(rows, platform)
    scores = -artifact["pipeline"].score_samples(frame)
    global_ref = artifact["reference"]
    group_refs = artifact.get("peer_references", {})
    peers = (frame["account_type"].astype(str) + "|" + frame["department"].astype(str)).to_numpy()
    return [float(np.searchsorted((reference := group_refs.get(peer, global_ref)), value, side="right") / len(reference))
            for value, peer in zip(scores, peers)]


def platform_status():
    """Model file availability only; check integrity on scoring/loading."""
    result = {}
    for key in SUPPORTED_MODELS:
        path = platform_path(key)
        result[key] = {"trained_artifact_present": path.exists(),
                       "manifest_present": path.with_suffix(".json").exists(),
                       "model_name": key, "schema": MODEL_SCHEMA_VERSION}
    return result
