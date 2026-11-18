from __future__ import annotations

import os
from typing import Any

from .ml.platform_models import (
    MODEL_SCHEMA_VERSION,
    SUPPORTED_MODELS,
    load_platform,
    platform_key,
    platform_status,
    predict_platform,
    prepare_platform,
)

SERVICE_NAME = "AccessGuard Quarterly ML Service"
SERVICE_VERSION = "9.0.0"
SUPPORTED_WINDOW_DAYS = 90
MIN_COVERAGE_FRACTION = float(os.getenv("MIN_MODEL_COVERAGE_FRACTION", "0.995"))

# These are metadata/identity fields and must never become model features.
FORBIDDEN_FEATURE_KEYS = {
    "username", "user_name", "email", "user_email", "employee_name",
    "full_name", "manager_name", "ip_address", "source_ip", "raw_message",
    "password", "token", "access_token", "group_id", "label", "ml_eval_label",
    "review_required", "review_outcome", "decision", "account_id", "employee_id",
}


def load_model_registry() -> tuple[dict[str, dict], dict[str, str]]:
    """Load trusted, hash-verified model artifacts. Never fit during inference."""
    registry: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for platform in SUPPORTED_MODELS:
        try:
            artifact = load_platform(platform)
            if artifact is None:
                errors[platform] = "model_not_trained"
            else:
                registry[platform] = artifact
        except Exception as exc:  # keep other platform services available
            errors[platform] = f"model_load_error:{type(exc).__name__}"
    return registry, errors


def _forbidden_key(features: dict[str, Any]) -> str | None:
    for key in features:
        if str(key).strip().casefold() in FORBIDDEN_FEATURE_KEYS:
            return str(key)
    return None


def _coverage_is_sufficient(features: dict[str, Any], window_days: int) -> bool:
    known = features.get("log_coverage_known")
    days = features.get("log_coverage_days")
    try:
        known_value = int(known)
        coverage_days = float(days)
    except (TypeError, ValueError):
        return False
    return (
        known_value == 1
        and coverage_days >= MIN_COVERAGE_FRACTION * window_days
        and coverage_days <= window_days + 0.01
    )


def _model_info(artifact: dict | None) -> dict[str, Any]:
    if not artifact:
        return {}
    metadata = artifact.get("metadata", {})
    return {
        "model_key": artifact.get("model_key"),
        "model_schema": artifact.get("schema"),
        "model_trained_utc": metadata.get("trained_utc"),
        "algorithm": metadata.get("algorithm", "IsolationForest"),
    }


def build_model_status(registry: dict[str, dict], errors: dict[str, str]) -> dict[str, Any]:
    raw = platform_status()
    result: dict[str, Any] = {}
    for platform in SUPPORTED_MODELS:
        artifact = registry.get(platform)
        metadata = artifact.get("metadata", {}) if artifact else {}
        result[platform] = {
            **raw.get(platform, {}),
            "loaded": artifact is not None,
            "status": "loaded" if artifact else errors.get(platform, "model_not_trained"),
            "algorithm": metadata.get("algorithm", "IsolationForest"),
            "trees": metadata.get("trees"),
            "feature_count": len(metadata.get("features", [])),
            "trained_utc": metadata.get("trained_utc"),
            "evaluation": metadata.get("evaluation", {}),
            "evaluation_provenance": metadata.get("evaluation", {}).get(
                "eval_provenance", "No evaluation metadata"
            ),
        }
    return {
        "service": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "model_schema": MODEL_SCHEMA_VERSION,
        "supported_platforms": list(SUPPORTED_MODELS),
        "models_loaded": len(registry),
        "all_models_loaded": len(registry) == len(SUPPORTED_MODELS),
        "models": result,
        "inference_policy": "load-only; no fit/retrain on scoring requests",
    }


def score_accounts(
    records: list[dict[str, Any]],
    window_days: int,
    registry: dict[str, dict],
    errors: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Score eligible account-window rows using an already-trained platform model.

    One row is one technical account for one review period. Only 90-day rows with
    explicitly attested >=99.5% usage-telemetry coverage are eligible for the
    Isolation Forest. Policy/lifecycle rules are intentionally handled by the
    main AccessGuard backend, not here.
    """
    errors = errors or {}
    results: list[dict[str, Any] | None] = [None] * len(records)
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {p: [] for p in SUPPORTED_MODELS}

    for index, record in enumerate(records):
        account_id = str(record.get("account_id", ""))
        raw_platform = str(record.get("platform", ""))
        canonical = platform_key(raw_platform)
        base = {
            "account_id": account_id,
            "platform": raw_platform,
            "status": "unscored",
            "reason": None,
            "model_key": canonical,
            "model_schema": None,
            "model_trained_utc": None,
            "algorithm": None,
            "anomaly_percentile_0_1": None,
            "anomaly_percentile_100": None,
        }

        if window_days != SUPPORTED_WINDOW_DAYS:
            base["reason"] = "model_window_mismatch:models_require_90_day_windows"
            results[index] = base
            continue
        if canonical is None:
            base["reason"] = "unsupported_platform:no_cross_platform_fallback"
            results[index] = base
            continue

        features = dict(record.get("features") or {})
        bad_key = _forbidden_key(features)
        if bad_key:
            base["reason"] = f"forbidden_identity_or_label_feature:{bad_key}"
            results[index] = base
            continue
        if "platform" in features and platform_key(features["platform"]) != canonical:
            base["reason"] = "platform_feature_mismatch"
            results[index] = base
            continue
        if not _coverage_is_sufficient(features, window_days):
            base["reason"] = "insufficient_or_unattested_90_day_log_coverage"
            results[index] = base
            continue

        artifact = registry.get(canonical)
        if artifact is None:
            base["reason"] = errors.get(canonical, "model_not_trained")
            results[index] = base
            continue

        row = {**features, "platform": raw_platform}
        try:
            # Validate one row independently, so a malformed row does not block
            # correctly formed rows from the same platform batch.
            prepare_platform([row], canonical)
        except Exception as exc:
            base["reason"] = f"invalid_features:{str(exc)[:240]}"
            results[index] = base
            continue
        grouped[canonical].append((index, row))

    for platform, items in grouped.items():
        if not items:
            continue
        artifact = registry[platform]
        scores = predict_platform([row for _, row in items], artifact)
        info = _model_info(artifact)
        for (index, _), score in zip(items, scores):
            percentile = max(0.0, min(1.0, float(score)))
            results[index] = {
                **{key: records[index].get(key) for key in ("account_id", "platform")},
                "status": "scored",
                "reason": None,
                **info,
                "anomaly_percentile_0_1": round(percentile, 6),
                "anomaly_percentile_100": round(percentile * 100, 2),
            }

    # Defensive guarantee: response cardinality/order always matches request.
    return [row if row is not None else {
        "account_id": str(records[i].get("account_id", "")),
        "platform": str(records[i].get("platform", "")),
        "status": "unscored", "reason": "internal_unscored_fallback",
        "model_key": None, "model_schema": None, "model_trained_utc": None,
        "algorithm": None, "anomaly_percentile_0_1": None,
        "anomaly_percentile_100": None,
    } for i, row in enumerate(results)]
