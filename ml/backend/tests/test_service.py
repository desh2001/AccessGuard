from __future__ import annotations

from pathlib import Path

import pytest

from app.ml.platform_models import MODEL_SCHEMA_VERSION, PLATFORM_CONFIG
from app.service import load_model_registry, score_accounts


def windows_features():
    cfg = PLATFORM_CONFIG["windows"]
    row = {name: "it" for name in cfg["categorical"]}
    for name in cfg["numeric"]:
        row[name] = 0
    row.update({
        "log_coverage_known": 1,
        "log_coverage_days": 90,
        "use_evidence_observed": 1,
        "windows_privileged_logon_coverage_known": 1,
    })
    return row


def test_missing_artifacts_do_not_train_or_load_a_fake_model(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_PLATFORM_MODEL_DIR", str(tmp_path))
    registry, errors = load_model_registry()
    assert registry == {}
    assert errors == {
        "windows": "model_not_trained",
        "linux": "model_not_trained",
        "github": "model_not_trained",
    }


def test_missing_model_returns_explicit_unscored_status():
    result = score_accounts(
        [{"account_id": "a-1", "platform": "Windows AD", "features": windows_features()}],
        90, {}, {"windows": "model_not_trained"},
    )
    assert result[0]["status"] == "unscored"
    assert result[0]["reason"] == "model_not_trained"
    assert result[0]["anomaly_percentile_0_1"] is None


def test_wrong_window_is_not_scored():
    result = score_accounts(
        [{"account_id": "a-1", "platform": "Windows AD", "features": windows_features()}],
        60, {}, {},
    )
    assert result[0]["reason"] == "model_window_mismatch:models_require_90_day_windows"


def test_unknown_platform_does_not_fall_back_to_another_model():
    result = score_accounts(
        [{"account_id": "a-1", "platform": "GitLab", "features": windows_features()}],
        90, {"windows": {"model_key": "windows"}}, {},
    )
    assert result[0]["status"] == "unscored"
    assert result[0]["reason"] == "unsupported_platform:no_cross_platform_fallback"


def test_insufficient_or_unknown_coverage_is_not_scored():
    features = windows_features()
    features["log_coverage_known"] = 0
    result = score_accounts(
        [{"account_id": "a-1", "platform": "Windows AD", "features": features}],
        90, {"windows": {"model_key": "windows"}}, {},
    )
    assert result[0]["reason"] == "insufficient_or_unattested_90_day_log_coverage"


def test_identity_and_training_labels_are_rejected_as_features():
    features = windows_features()
    features["username"] = "alice"
    result = score_accounts(
        [{"account_id": "a-1", "platform": "Windows AD", "features": features}],
        90, {"windows": {"model_key": "windows"}}, {},
    )
    assert result[0]["reason"] == "forbidden_identity_or_label_feature:username"


def test_valid_row_uses_loaded_model_and_returns_advisory_percentile(monkeypatch):
    import app.service as service

    artifact = {
        "model_key": "windows",
        "schema": MODEL_SCHEMA_VERSION,
        "metadata": {
            "trained_utc": "2026-01-01T00:00:00+00:00",
            "algorithm": "IsolationForest",
        },
    }
    monkeypatch.setattr(service, "predict_platform", lambda rows, model: [0.876543])
    result = service.score_accounts(
        [{"account_id": "opaque-001", "platform": "Windows AD", "features": windows_features()}],
        90, {"windows": artifact}, {},
    )
    assert result[0]["status"] == "scored"
    assert result[0]["model_key"] == "windows"
    assert result[0]["anomaly_percentile_0_1"] == 0.876543
    assert result[0]["anomaly_percentile_100"] == 87.65


def test_duplicate_ids_are_validated_by_endpoint_not_feature_schema():
    from app.schemas import ScoreAccountsRequest
    from pydantic import ValidationError

    body = {
        "cycle_id": "cycle-1", "window_days": 90,
        "records": [
            {"account_id": "same", "platform": "Linux", "features": {}},
            {"account_id": "same", "platform": "Windows AD", "features": {}},
        ],
    }
    # Duplicate IDs are intentionally validated at the endpoint (because this
    # schema alone does not know whether IDs are unique across the batch).
    parsed = ScoreAccountsRequest.model_validate(body)
    assert len(parsed.records) == 2
