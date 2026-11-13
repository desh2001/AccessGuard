"""Explainable review-priority policy + optional independently trained anomaly model.

Neither policy points nor ML anomaly rarity proves misuse, nor authorizes automatic removal.
"""
import logging
from sqlalchemy.orm import Session, joinedload
from .models import Entitlement, Account, utcnow
from .ml.features import PRIVILEGED, EXPECTED_ACCESS, outside_role, entitlement_features
from .ml.model import load_model, score_rows

logger = logging.getLogger(__name__)


def recompute(db: Session) -> dict:
    entitlements = db.query(Entitlement).options(joinedload(Entitlement.account).joinedload(Account.employee)).all()
    now = utcnow()
    active = [e for e in entitlements if e.active]
    model_used = False
    model_issue = None
    scores = {}
    if active:
        try:
            artifact = load_model()
            if artifact is not None:
                rows = [entitlement_features(e, now) for e in active]
                results = score_rows(rows, artifact)
                scores = dict(zip((e.id for e in active), results))
                model_used = True
        except (OSError, ValueError, KeyError, ImportError, EOFError) as exc:
            # Fail open for visibility, but fall back to deterministic policy scoring.
            # Never claim to have used ML if its artifact is incompatible or corrupt.
            model_issue = type(exc).__name__
            logger.warning("ML artifact unavailable; using rule-only scoring (%s)", model_issue)
    for e in entitlements:
        if not e.active:
            e.risk_score = 0
            e.risk_level = "inactive"
            e.reasons = ["Entitlement is not currently reported as active"]
            e.anomaly_score = None
            continue
        score, reasons = 0, []
        emp = e.account.employee
        if emp is None:
            score += 40
            reasons.append("Orphaned account: no verified employee identity mapping (+40)")
        elif emp.status.lower() != "active":
            score += 45
            reasons.append("Employee lifecycle status is not active (+45)")
        privileged = e.permission.lower() in PRIVILEGED
        if privileged:
            score += 20
            reasons.append("Privileged role requires additional scrutiny (+20)")
        if e.sensitivity.lower() in {"high", "critical"}:
            score += 15
            reasons.append("High-sensitivity resource (+15)")
        if emp and outside_role(emp.department, e.resource):
            score += 25
            reasons.append("Resource outside configured department access policy (+25)")
        if e.last_used_at:
            days = max(0, (now - e.last_used_at).days)
            if days >= 90:
                score += 25
                reasons.append(f"Verified resource-use evidence is {days} days old (+25)")
            elif days >= 60:
                score += 10
                reasons.append(f"Verified resource-use evidence is {days} days old (+10)")
        else:
            reasons.append("Resource-use evidence unavailable; cannot establish inactivity")
        if e.account.last_login and (now - e.account.last_login).days >= 90:
            score += 10
            reasons.append("Account last login older than 90 days (+10)")
        # The empirical percentile is not a probability of misuse or a risk score.
        prediction = scores.get(e.id)
        e.anomaly_score = prediction["anomaly_percentile"] if prediction else None
        if prediction and prediction["is_anomaly"]:
            score += 10
            pct = round(100 * prediction["anomaly_percentile"], 1)
            reasons.append(f"ML statistical anomaly at {pct}th percentile of the normal training reference (+10; review only)")
        e.risk_score = min(score, 100)
        e.risk_level = "high" if e.risk_score >= 70 else "medium" if e.risk_score >= 35 else "low"
        e.reasons = reasons or ["No configured risk rules triggered"]
    db.flush()
    return {
        "analyzed": len(entitlements),
        "high": sum(e.risk_level == "high" for e in active),
        "medium": sum(e.risk_level == "medium" for e in active),
        "anomaly_model_used": model_used,
        "ml_status": "loaded" if model_used else "unavailable" if model_issue else "not_trained_or_no_active_records",
        "ml_issue": model_issue,
    }
