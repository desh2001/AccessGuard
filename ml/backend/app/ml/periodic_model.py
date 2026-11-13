"""Quarterly access review anomaly model: offline fit, read-only inference.
Anomaly rarity is not the probability of unnecessary access or a revocation decision.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import hashlib
import hmac
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
from .periodic_features import CATEGORICAL, NUMERIC, FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION

DEFAULT_PERIODIC_PATH = Path(__file__).resolve().parents[2] / 'ml_artifacts' / 'periodic_review_model.joblib'


def periodic_path():
    return Path(os.getenv('PERIODIC_ML_MODEL_PATH') or DEFAULT_PERIODIC_PATH).resolve()


def prepare_frame(rows):
    frame = pd.DataFrame(rows)
    missing = set(FEATURE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing periodic feature columns: {sorted(missing)}')
    frame = frame[FEATURE_COLUMNS].copy()
    for col in CATEGORICAL:
        frame[col] = frame[col].fillna('unknown').astype(str).str.lower()
    for col in NUMERIC:
        frame[col] = pd.to_numeric(frame[col], errors='raise').fillna(0)
        if (frame[col] < 0).any():
            raise ValueError(f'{col} contains negative values')
    for flag in ('use_evidence_observed', 'log_coverage_known'):
        if not frame[flag].isin((0, 1)).all():
            raise ValueError(f'{flag} must be 0/1')
    # Prevent unknown coverage or use timestamps from being interpreted as zeros.
    frame.loc[frame.log_coverage_known == 0, 'log_coverage_days'] = 0
    frame.loc[frame.use_evidence_observed == 0, 'use_age_days'] = 0
    return frame


def pipeline(seed=42, n_estimators=160):
    return Pipeline([
        ('preprocessor', ColumnTransformer([
            ('cat', OneHotEncoder(handle_unknown='ignore'), CATEGORICAL),
            ('num', StandardScaler(), NUMERIC),
        ])),
        ('detector', IsolationForest(n_estimators=n_estimators, contamination='auto', random_state=seed, n_jobs=1)),
    ])


def train_periodic(data, seed=42, n_estimators=160):
    if not 50 <= n_estimators <= 1000:
        raise ValueError('n_estimators must be between 50 and 1000')
    if not {'label','group_id'}.issubset(data.columns):
        raise ValueError('Need independent label and account group_id')
    if len(data) < 150:
        raise ValueError('Need at least 150 records')
    labels = pd.to_numeric(data.label, errors='raise')
    if labels.isna().any() or not labels.isin((0,1)).all():
        raise ValueError('label must be 0 or 1')
    if data.group_id.isna().any():
        raise ValueError('group_id cannot be missing')
    x = prepare_frame(data)
    train_indices, test_indices = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=seed).split(x, labels, data.group_id))
    normal_train = x.iloc[train_indices].loc[labels.iloc[train_indices] == 0]
    if len(normal_train) < 80:
        raise ValueError('Need >= 80 confirmed normal train rows')
    model = pipeline(seed, n_estimators=n_estimators)
    model.fit(normal_train)
    normal_scores = -model.score_samples(normal_train)
    normal_reference = np.sort(normal_scores)
    # Compare accounts to similar platform/account-type peers when enough
    # reference samples exist. Sparse cohorts fall back to the global baseline.
    peer_references = {}
    peers = (normal_train['platform'].astype(str) + '|' + normal_train['account_type'].astype(str)).to_numpy()
    for peer in np.unique(peers):
        group_scores = normal_scores[peers == peer]
        if len(group_scores) >= 40:
            peer_references[str(peer)] = np.sort(group_scores)
    holdout_scores = -model.score_samples(x.iloc[test_indices])
    test_labels = labels.iloc[test_indices].to_numpy()
    metrics = {
        'holdout_rows': len(test_indices), 'holdout_positives': int(test_labels.sum()),
        'holdout_groups': int(data.iloc[test_indices].group_id.nunique()),
    }
    if len(set(test_labels)) == 2:
        metrics['roc_auc'] = round(float(roc_auc_score(test_labels, holdout_scores)), 4)
        metrics['average_precision'] = round(float(average_precision_score(test_labels, holdout_scores)), 4)
        # Model-only capacity measure. Actual hybrid queue must be evaluated separately.
        for pct in (0.05, 0.10, 0.20):
            k = max(1, int(np.ceil(len(holdout_scores) * pct)))
            chosen = np.argsort(-holdout_scores)[:k]
            hits = int(test_labels[chosen].sum())
            metrics[f'precision_at_{int(pct*100)}pct'] = round(hits / k, 4)
            metrics[f'recall_at_{int(pct*100)}pct'] = round(hits / test_labels.sum(), 4) if test_labels.sum() else None
    artifact = {
        'pipeline': model, 'reference': normal_reference, 'peer_references': peer_references,
        'schema': FEATURE_SCHEMA_VERSION,
        'metadata': {'model':'IsolationForest', 'schema': FEATURE_SCHEMA_VERSION,
                     'trained_utc': datetime.now(timezone.utc).isoformat(), 'seed': seed,
                     'n_estimators':n_estimators, 'contamination':'auto',
                     'rationale':'Provisional unsupervised outlier baseline for offline account-level quarterly reviews; verify against full manual reviews before selection',
                     'normal_training_rows': len(normal_train), 'peer_groups': {k:len(v) for k,v in peer_references.items()}, 'evaluation': metrics,
                     'disclaimer': 'Synthetic demonstration unless externally labeled; anomaly != unsafe.'},
    }
    return artifact


def save_periodic(artifact, path=None):
    path = Path(path or periodic_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.joblib', delete=False) as f:
        temporary = Path(f.name)
    try:
        joblib.dump(artifact, temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    # Digest catches accidental changes. HMAC is required in hardened deployments
    # because a plain hash plus an editable manifest is NOT a trusted signature.
    binary_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = {**artifact['metadata'], 'artifact_sha256':binary_digest}
    signing_key = os.getenv('AEGIS_MODEL_SIGNING_KEY')
    if signing_key:
        metadata['artifact_hmac_sha256'] = hmac.new(signing_key.encode(),
                             binary_digest.encode(), hashlib.sha256).hexdigest()
    sidecar = path.with_suffix('.json')
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                     suffix='.json',delete=False) as m:
        tmp_sidecar = Path(m.name)
        json.dump(metadata,m,indent=2)
    tmp_sidecar.replace(sidecar)


def load_periodic():
    path = periodic_path()
    if not path.exists():
        return None
    # joblib/pickle executes code while loading; verify approved artifact storage,
    # integrity and (if enabled) keyed signature BEFORE deserializing.
    sidecar = path.with_suffix('.json')
    if not sidecar.exists():
        raise ValueError('Missing model provenance manifest')
    metadata = json.loads(sidecar.read_text(encoding='utf-8'))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hmac.compare_digest(str(metadata.get('artifact_sha256','')),digest):
        raise ValueError('Model artifact digest mismatch')
    signing_key=os.getenv('AEGIS_MODEL_SIGNING_KEY')
    require_signature = os.getenv('AEGIS_REQUIRE_SIGNED_MODELS','false').strip().lower() == 'true'
    if require_signature and not signing_key:
        raise ValueError('AEGIS_MODEL_SIGNING_KEY is mandatory when signature enforcement is enabled')
    if signing_key:
        expected=hmac.new(signing_key.encode(),digest.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(metadata.get('artifact_hmac_sha256','')),expected):
            raise ValueError('Missing/invalid model HMAC signature')
    artifact = joblib.load(path)
    if artifact.get('metadata',{}).get('schema') != metadata.get('schema'):
        raise ValueError('Model manifest/embedded metadata mismatch')
    if artifact.get('schema') != FEATURE_SCHEMA_VERSION:
        raise ValueError('Periodic model schema mismatch; retrain')
    return artifact


def predict_periodic(rows, artifact):
    if not rows:
        return []
    frame = prepare_frame(rows)
    scores = -artifact['pipeline'].score_samples(frame)
    global_reference = artifact['reference']
    by_peer = artifact.get('peer_references', {})
    peers = (frame['platform'].astype(str) + '|' + frame['account_type'].astype(str)).to_numpy()
    result = []
    for score, peer in zip(scores, peers):
        reference = by_peer.get(str(peer), global_reference)
        result.append(float(np.searchsorted(reference, score, side='right') / len(reference)))
    return result
