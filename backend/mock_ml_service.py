"""Standalone Service for `Dialog-Project-Final-ML` (Hashan's Repo - Aegis V8).

Run independently in a separate terminal:
    python -m uvicorn mock_ml_service:app --port 8001 --host 127.0.0.1

This simulates the external machine learning service that predicts risk
scores and anomaly percentiles for Dialog enterprise access entitlements across
the three independent platform models (Windows, Linux, GitHub).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel
import numpy as np
from sklearn.ensemble import IsolationForest

app = FastAPI(
    title="Dialog Final ML Microservice (Aegis V8)",
    version="1.4.0",
    description="Multi-Platform Machine Learning Risk Engine for Dialog Access Governance.",
)

PLATFORMS_DIR = Path(__file__).resolve().parent.parent / 'ml' / 'backend' / 'ml_artifacts' / 'platforms'


class GrantItem(BaseModel):
    grant_id: int
    identity_id: str | None = None
    identity_name: str | None = None
    department: str | None = None
    system_id: str | None = None
    permission: str | None = None
    resource: str | None = None
    privilege: int = 0
    cross_department: int = 0
    last_verified_use: str | None = None
    rule_score: int = 10


class PredictRequest(BaseModel):
    grants: list[GrantItem]


def get_platform_specs() -> dict[str, Any]:
    specs = {}
    if PLATFORMS_DIR.exists():
        for name in ('windows', 'linux', 'github'):
            p = PLATFORMS_DIR / f"{name}.json"
            if p.exists():
                try:
                    specs[name] = json.loads(p.read_text(encoding='utf-8'))
                except Exception:
                    pass
    return specs


@app.get("/health")
def health():
    specs = get_platform_specs()
    return {
        "status": "healthy",
        "service_name": "Dialog-Project-Final-ML",
        "model_version": "v1.4-production (Aegis V8)",
        "algorithm": "Platform-Specific IsolationForest (Windows, Linux, GitHub)",
        "author": "Dialog ML Team (Hashan)",
        "platforms_loaded": list(specs.keys()) if specs else ["windows", "linux", "github"],
    }


@app.get("/api/ml/platforms")
def platform_models():
    specs = get_platform_specs()
    return {
        "status": "active",
        "platforms": specs,
    }


@app.post("/predict-risk")
def predict_risk(payload: PredictRequest):
    grants = payload.grants
    if not grants:
        return {"mode": "empty", "findings": [], "samples": 0}

    # Extract feature matrix for IsolationForest
    # Features: [privilege, cross_dept, rule_score_norm, is_admin]
    X = np.array([
        [
            float(g.privilege),
            float(g.cross_department),
            float(g.rule_score) / 100.0,
            float(g.permission == 'Admin' or g.privilege == 1),
        ]
        for g in grants
    ], dtype=float)

    # Train IsolationForest on batch
    contamination = 0.12
    clf = IsolationForest(n_estimators=160, contamination=contamination, random_state=42)
    clf.fit(X)
    scores = -clf.decision_function(X)

    # Convert to percentiles
    order = np.argsort(np.argsort(scores, kind='stable'), kind='stable')
    denom = max(1, len(grants) - 1)

    findings = []
    for idx, g in enumerate(grants):
        percentile = round(100 * float(order[idx]) / denom)
        combined = round(0.65 * g.rule_score + 0.35 * percentile)
        level = "Critical" if combined >= 85 else ("High" if combined >= 60 else ("Medium" if combined >= 35 else "Low"))
        
        # Match platform
        sys_code = (g.system_id or '').upper()
        if 'WIN' in sys_code or 'AD' in sys_code:
            platform_tag = "Windows AD Model (ROC-AUC: 0.920)"
        elif 'LIN' in sys_code or 'UBUNTU' in sys_code or 'CENTOS' in sys_code:
            platform_tag = "Linux PAM Model (ROC-AUC: 0.949)"
        elif 'GH' in sys_code or 'GIT' in sys_code:
            platform_tag = "GitHub OAuth Model (ROC-AUC: 0.969)"
        else:
            platform_tag = "Cross-Platform Ensemble"

        reasons = []
        if g.privilege:
            reasons.append("High privilege administrative grant")
        if g.cross_department:
            reasons.append("Cross-department boundary violation")
        if percentile >= 85:
            reasons.append(f"Structural anomaly detected by {platform_tag}")
        if not reasons:
            reasons.append("Standard cohort entitlement pattern")

        rec = (
            "Escalate for urgent review" if combined >= 80 or g.rule_score >= 85
            else ("Request human review" if combined >= 60 or g.rule_score >= 60 else "Monitor")
        )

        findings.append({
            "grant_id": g.grant_id,
            "identity_name": g.identity_name or "Unknown",
            "system_name": g.system_id or "Unknown",
            "permission": g.permission or "Unknown",
            "department": g.department or "Unknown",
            "rule_score": g.rule_score,
            "anomaly_percentile": percentile,
            "combined_priority": combined,
            "combined_level": level,
            "reasons": reasons,
            "recommendation": rec,
            "model": f"Dialog-Project-Final-ML ({platform_tag})",
            "platform_model": platform_tag,
        })

    findings.sort(key=lambda r: (r["combined_priority"], r["rule_score"]), reverse=True)
    urgent = sum(1 for f in findings if f["recommendation"] == "Escalate for urgent review")
    review = sum(1 for f in findings if f["recommendation"] == "Request human review")

    return {
        "mode": "external-dialog-ml",
        "algorithm": "Dialog Final Multi-Platform IsolationForest (Aegis V8)",
        "samples": len(grants),
        "summary": {
            "urgent": urgent,
            "needs_review": review,
            "monitor": len(findings) - urgent - review,
        },
        "metric_note": "Multi-platform predictions computed by Dialog-Project-Final-ML microservice.",
        "findings": findings,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_ml_service:app", host="127.0.0.1", port=8001, reload=True)
