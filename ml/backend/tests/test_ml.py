"""Tests for ML feature semantics, evaluation, persistence and risk integration."""
from datetime import timedelta
import json

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Account, Employee, Entitlement, utcnow
from app.ml.features import FEATURE_COLUMNS, entitlement_features
from app.ml.generate import generate_rows
from app.ml.model import (load_model, model_status, normalized_frame, save_artifact,
                          score_rows, train_dataframe)
from app.risk import recompute


@pytest.fixture(scope="module")
def prepared_artifact():
    # Trains only on synthetic normal examples and evaluates on separate groups.
    frame = pd.DataFrame(generate_rows(normal=360, anomalous=100, seed=23))
    artifact, metadata = train_dataframe(frame, seed=13, n_estimators=60)
    return artifact, metadata


def test_train_evaluation_has_labels_separated_and_schema(prepared_artifact):
    artifact, metadata = prepared_artifact
    assert metadata["feature_schema_version"] == "1.0"
    assert metadata["training_normal_rows"] >= 80
    assert metadata["heldout_rows"] > 0
    assert metadata["evaluation"]["heldout_positive_count"] > 0
    assert 0 <= metadata["evaluation"]["precision"] <= 1
    assert sum(metadata["evaluation"]["confusion_matrix_tn_fp_fn_tp"]) == metadata["heldout_rows"]
    assert "employee_name" not in FEATURE_COLUMNS
    predictions = score_rows(pd.DataFrame(generate_rows(10, 4)).to_dict(orient="records"), artifact)
    assert len(predictions) == 14
    assert all(0 <= r["anomaly_percentile"] <= 1 for r in predictions)


def test_missing_use_is_not_dormancy_and_clean_training_validation():
    row = generate_rows(1, 1)[0]
    row["resource_use_observed"] = 0
    row["last_used_days"] = 365
    row["last_login_observed"] = 0
    row["last_login_days"] = 250
    frame = normalized_frame(pd.DataFrame([row]))
    assert frame.iloc[0]["last_used_days"] == 0
    assert frame.iloc[0]["last_login_days"] == 0
    with pytest.raises(ValueError, match="Missing required"):
        normalized_frame(pd.DataFrame({"department": ["IT"]}))
    with pytest.raises(ValueError, match="Labels must be"):
        bad = pd.DataFrame(generate_rows(360, 100))
        bad.loc[0, "label"] = 7
        train_dataframe(bad)


def test_artifact_serialization_status_and_back_end_scoring(prepared_artifact, tmp_path, monkeypatch):
    artifact, metadata = prepared_artifact
    path = tmp_path / "access_anomaly_model.joblib"
    save_artifact(artifact, path)
    monkeypatch.setenv("ML_MODEL_PATH", str(path))
    assert json.loads(path.with_suffix(".json").read_text())["model"] == "IsolationForest"
    loaded = load_model()
    assert loaded is not None
    assert model_status()["ready"] is True

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        employee = Employee(code="E-TEST", name="Test User", email="test@example.test",
                            department="Finance", job_title="Analyst", status="active")
        db.add(employee)
        db.flush()
        acc = Account(employee_id=employee.id, platform="Linux", username="testuser",
                      status="active", last_login=utcnow() - timedelta(days=4))
        db.add(acc)
        db.flush()
        ent = Entitlement(account_id=acc.id, resource="dev:production-db", permission="admin",
                          sensitivity="critical", last_used_at=None, active=True)
        db.add(ent)
        db.flush()
        feats = entitlement_features(ent, utcnow())
        assert feats["resource_use_observed"] == 0
        assert feats["last_used_days"] == 0
        result = recompute(db)
        assert result["anomaly_model_used"] is True
        assert 0 <= ent.anomaly_score <= 1
        assert any("unavailable" in reason for reason in ent.reasons)
        assert ent.risk_score >= 60  # role mismatch + privilege + sensitivity
    engine.dispose()


def test_model_missing_falls_back_to_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_MODEL_PATH", str(tmp_path / "missing.joblib"))
    assert model_status()["state"] == "not_trained"
