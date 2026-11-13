import os
import io
import csv
import json
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from .db import Base, engine, get_db, SessionLocal
from .models import User, Employee, Account, Entitlement, Review, Audit, PeriodicReviewCycle, PeriodicAccountReview, TransferAccessDisposition, EmployeeTransfer, utcnow
from .security import current_user, admin_only, verify_password, create_token
from .risk import recompute
from .ml.model import model_status
from .ml.platform_models import platform_status
from .ml.periodic_queue import periodic_preview
from .seed import seed_demo
from .importers import import_csv
from .github_connector import sync_github

@asynccontextmanager
async def lifespan(app: FastAPI):
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32 or "CHANGE_ME" in secret:
        raise RuntimeError("Set JWT_SECRET to a random secret of at least 32 characters")
    if os.getenv("SEED_DEMO", "false").lower() == "true":
        if any(not os.environ.get(name) or "CHANGE_ME" in os.environ[name] for name in ("DEMO_ADMIN_PASSWORD", "DEMO_REVIEWER_PASSWORD")):
            raise RuntimeError("Configure strong DEMO_ADMIN_PASSWORD and DEMO_REVIEWER_PASSWORD")
    Base.metadata.create_all(engine)  # MVP only: replace with Alembic migrations in production
    if os.getenv("SEED_DEMO", "false").lower() == "true":
        with SessionLocal() as db:
            seed_demo(db)
    yield

app = FastAPI(title="Aegis Access Governance API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","), allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

class LoginInput(BaseModel):
    username: str
    password: str

class CreateReviewInput(BaseModel):
    risk_levels: list[Literal["high", "medium", "low"]] = ["high", "medium"]

class ReviewCycleInput(BaseModel):
    window_days: int = Field(default=90, ge=30, le=365)
    review_budget_percent: float = Field(default=10.0, gt=0, le=100)
    policy_threshold: int = Field(default=25, ge=0, le=100)
    anomaly_threshold: float = Field(default=0.95, gt=0, le=1)

class DecideInput(BaseModel):
    decision: Literal["retain", "revoke"]
    reason: str = Field(min_length=5, max_length=1000)

def audit(db: Session, actor: str, action: str, kind: str, entity_id, details=None):
    db.add(Audit(actor=actor, action=action, entity_type=kind, entity_id=str(entity_id), details=details or {}))

def resolve_application_owner(platform: str, valid_reviewers: set[str],
                              employee_manager: str | None, fallback: str) -> str:
    """Prefer app/system owner mapping over a line manager for periodic certifications.

    Mapping is a competition MVP environment setting. A production deployment
    must use authoritative application-owner assignments with change control.
    """
    try:
        mapping = json.loads(os.getenv('PLATFORM_REVIEWERS_JSON', '{}'))
        if not isinstance(mapping, dict):
            mapping = {}
    except json.JSONDecodeError:
        mapping = {}
    selected = mapping.get(platform)
    if isinstance(selected, str) and selected in valid_reviewers:
        return selected
    if employee_manager and employee_manager in valid_reviewers:
        return employee_manager
    return 'reviewer' if 'reviewer' in valid_reviewers else fallback


def ent_to_dict(e: Entitlement):
    account = e.account
    emp = account.employee
    return {
        "id": e.id, "employee": emp.name if emp else "Unmapped identity", "employee_code": emp.code if emp else "—",
        "department": emp.department if emp else "Unknown", "employee_status": emp.status if emp else "unknown",
        "account_id": account.id, "account_username": account.username, "platform": account.platform,
        "resource": e.resource, "permission": e.permission, "sensitivity": e.sensitivity,
        "source": e.source, "active": e.active, "last_used_at": e.last_used_at,
        "evidence_source": e.evidence_source, "last_login": account.last_login,
        "risk_score": e.risk_score, "risk_level": e.risk_level,
        "reasons": e.reasons or [], "anomaly_score": e.anomaly_score,
        "anomaly_metric": "normal_reference_percentile_0_to_1" if e.anomaly_score is not None else None,
    }

def review_to_dict(r: Review):
    return {
        "id": r.id, "entitlement_id": r.entitlement_id, "assigned_to": r.assigned_to,
        "state": r.state, "reason": r.reason, "decided_by": r.decided_by,
        "requested_at": r.requested_at, "decided_at": r.decided_at,
        "remediation_state": r.remediation_state, "remediation_at": r.remediation_at,
        "entitlement": ent_to_dict(r.entitlement),
    }

@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "demo" if os.getenv("SEED_DEMO") == "true" else "standard"}

@app.post("/api/auth/login")
def login(body: LoginInput, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": create_token(user), "token_type": "bearer", "user": {"username": user.username, "display_name": user.display_name, "role": user.role}}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "display_name": user.display_name, "role": user.role}

@app.get("/api/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    ents = db.query(Entitlement).filter_by(active=True).all()
    reviews = db.query(Review).all()
    high = sum(e.risk_level == "high" for e in ents)
    med = sum(e.risk_level == "medium" for e in ents)
    return {
        "employees": db.query(Employee).count(), "accounts": db.query(Account).count(),
        "entitlements": len(ents), "high_risk": high, "medium_risk": med,
        "unmapped_accounts": db.query(Account).filter(Account.employee_id.is_(None)).count(),
        "pending_reviews": sum(r.state == "pending" for r in reviews),
        "completed_reviews": sum(r.state != "pending" for r in reviews),
        "simulated_remediations": sum(r.remediation_state == "simulated" for r in reviews),
        "risk_distribution": {"High": high, "Medium": med, "Low": len(ents)-high-med},
        "platform_distribution": {k: v for k, v in db.query(Account.platform, func.count(Account.id)).group_by(Account.platform).all()},
        "department_distribution": {k: v for k, v in db.query(Employee.department, func.count(Employee.id)).group_by(Employee.department).all()},
        "remediation_mode": "simulation_only",
    }

@app.get("/api/metrics")
def metrics(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Review)
    if user.role != "admin":
        q = q.filter(Review.assigned_to == user.username)
    reviews = q.all()
    decided = [r for r in reviews if r.state != "pending"]
    with_full_evidence = [r for r in decided if r.decided_at and r.decided_by and r.reason]
    decision_hours = [(r.decided_at-r.requested_at).total_seconds()/3600 for r in decided if r.decided_at]
    return {
        "reviews_assigned": len(reviews),
        "reviews_completed": len(decided),
        "review_completion_percent": round(100*len(decided)/len(reviews), 1) if reviews else None,
        "decision_evidence_completeness_percent": round(100*len(with_full_evidence)/len(decided), 1) if decided else None,
        "average_decision_hours": round(sum(decision_hours)/len(decision_hours), 2) if decision_hours else None,
        "remediation_upstream_verified_count": 0,
        "measurement_note": "No live revocation verification is implemented; model classification accuracy requires separately labeled validation cases.",
    }

@app.get("/api/employees")
def employees(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": e.id, "code": e.code, "name": e.name, "department": e.department, "job_title": e.job_title, "email": e.email, "status": e.status, "accounts": len(e.accounts)} for e in db.query(Employee).options(joinedload(Employee.accounts)).order_by(Employee.name).all()]

@app.get("/api/accounts")
def accounts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    records = db.query(Account).options(joinedload(Account.employee)).all()
    return [{"id": a.id, "username": a.username, "platform": a.platform, "employee": a.employee.name if a.employee else None, "last_login": a.last_login, "status": a.status, "synced_at": a.synced_at} for a in records]

@app.get("/api/entitlements")
def entitlements(risk: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = db.query(Entitlement).options(joinedload(Entitlement.account).joinedload(Account.employee))
    if risk:
        query = query.filter_by(risk_level=risk)
    return [ent_to_dict(e) for e in query.order_by(Entitlement.risk_score.desc(), Entitlement.id).all()]

@app.get("/api/reviews")
def reviews(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Review).options(joinedload(Review.entitlement).joinedload(Entitlement.account).joinedload(Account.employee))
    if user.role != "admin":
        q = q.filter(Review.assigned_to == user.username)
    return [review_to_dict(r) for r in q.order_by(Review.requested_at.desc(), Review.id.desc()).all()]

@app.get("/api/ml/status")
def ml_status(user: User = Depends(current_user)):
    """Read-only model status and honest evaluation provenance."""
    result = model_status()
    result['quarterly_review_models'] = platform_status()
    result['quarterly_review_model'] = {
        'loaded': False, 'legacy_shared_model_disabled': True,
        'note': 'Use three independent Windows/Linux/GitHub quarterly models.'}

    return result

@app.post("/api/risk/recompute")
def recompute_risk(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    result = recompute(db)
    audit(db, user.username, "RISK_RECOMPUTED", "risk", "all", result)
    db.commit()
    return result

@app.post("/api/review-cycles/preview")
def review_cycle_preview(body: ReviewCycleInput, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Rank historical account access for human review; does not certify or revoke."""
    return periodic_preview(db, window_days=body.window_days, review_budget_percent=body.review_budget_percent,
                            max_results=200, policy_threshold=body.policy_threshold, anomaly_threshold=body.anomaly_threshold)

@app.post("/api/review-cycles/create")
def review_cycle_create(body: ReviewCycleInput, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Persist ONE reviewer task per selected account; never grant/revoke access."""
    preview = periodic_preview(db, window_days=body.window_days, review_budget_percent=body.review_budget_percent,
                               policy_threshold=body.policy_threshold, anomaly_threshold=body.anomaly_threshold)
    selections = [a for a in preview["accounts"] if a["review_priority"] in ("mandatory", "selected")]
    cycle = PeriodicReviewCycle(
        review_window_days=body.window_days, review_budget_percent=body.review_budget_percent,
        window_end_at=utcnow(), created_by=user.username,
        total_accounts=preview["total_accounts"], selected_accounts=len(selections),
        mandatory_accounts=preview["mandatory_count"], model_used=preview["ml_model_used"])
    db.add(cycle)
    db.flush()
    account_ids = [a["account_id"] for a in selections]
    accounts = {a.id:a for a in db.query(Account).options(joinedload(Account.employee),joinedload(Account.entitlements))
                .filter(Account.id.in_(account_ids)).all()} if account_ids else {}
    valid_reviewers = {r[0] for r in db.query(User.username).all()}
    for item in selections:
        account = accounts[item["account_id"]]
        manager = account.employee.manager_username if account.employee else None
        reviewer = resolve_application_owner(account.platform, valid_reviewers, manager, user.username)
        db.add(PeriodicAccountReview(
            cycle_id=cycle.id, account_id=account.id, assigned_to=reviewer,
            priority=item["review_priority"], policy_score=item["policy_score"],
            anomaly_percentile=item["anomaly_percentile"],
            evidence_snapshot={"reasons":item["reasons"], "activity":item["activity_summary"],
                               "ranking_score":item["ranking_score"],
                               "policy_threshold":body.policy_threshold,
                               "anomaly_threshold":body.anomaly_threshold,
                               "ad_reporting_manager":item.get("reporting_manager_ref"),
                               "ad_org_unit":item.get("ad_org_unit"),
                               "evidence_sufficient_for_inactivity":item["evidence_sufficient_for_inactivity"],
                               "model_provenance":preview.get("model_provenance"),
                               "model_schema_version":item.get("ml_model_version"),
                               "ml_model_key":item.get("ml_model_key"),
                               "pending_transfer_ids":item.get("pending_transfer_ids", []),
                               "pending_transfer_count":item.get("pending_transfer_count", 0),
                               "evidence_gap":item.get("evidence_gap", False),
                               "employee_status_at_creation":item["employee_status"],
                               "grants":[{"resource":g.resource,"permission":g.permission,
                                          "sensitivity":g.sensitivity} for g in account.entitlements if g.active]}))
    audit(db, user.username, "PERIODIC_ACCOUNT_REVIEW_CYCLE_CREATED", "review_cycle", cycle.id,
          {"window_days":body.window_days, "budget_percent":body.review_budget_percent,
           "policy_threshold":body.policy_threshold, "anomaly_threshold":body.anomaly_threshold,
           "total_accounts":preview["total_accounts"], "selected_accounts":len(selections),
           "mandatory_accounts":preview["mandatory_count"], "ml_model_used":preview["ml_model_used"],
           "deferred_candidates":preview["deferred_candidate_count"],
           "insufficient_evidence":preview["insufficient_evidence_count"]})
    db.commit()
    return {"cycle_id":cycle.id,"selected_accounts":len(selections),"created_account_reviews":len(selections),
            "mandatory_accounts":preview["mandatory_count"],"model_used":preview["ml_model_used"],
            "note":"Account-level human certification tasks created. No automatic approval or removal."}


def account_task_dict(task: PeriodicAccountReview):
    acc = task.account
    return {"id":task.id,"cycle_id":task.cycle_id,"account_id":task.account_id,
            "platform":acc.platform,"username":acc.username,"employee":acc.employee.name if acc.employee else "Unmapped",
            "employee_status":acc.employee.status if acc.employee else "unmapped",
            "assigned_to":task.assigned_to,"priority":task.priority,"policy_score":task.policy_score,
            "anomaly_percentile":task.anomaly_percentile,"evidence":task.evidence_snapshot,
            "state":task.state,"rationale":task.rationale,"decided_by":task.decided_by,
            "decided_at":task.decided_at,"remediation_state":task.remediation_state}


@app.get("/api/review-cycles")
def list_review_cycles(db: Session = Depends(get_db), user: User = Depends(current_user)):
    cycles = db.query(PeriodicReviewCycle).order_by(PeriodicReviewCycle.created_at.desc(),PeriodicReviewCycle.id.desc()).limit(30).all()
    return [{"id":c.id,"window_days":c.review_window_days,"budget_percent":c.review_budget_percent,
             "total_accounts":c.total_accounts,"selected_accounts":c.selected_accounts,
             "mandatory_accounts":c.mandatory_accounts,"model_used":c.model_used,"created_at":c.created_at,
             "status":c.status} for c in cycles]


@app.get("/api/review-cycles/{cycle_id}/accounts")
def list_cycle_accounts(cycle_id: int, limit: int = Query(default=50,ge=1,le=500),
                        offset: int = Query(default=0,ge=0),
                        state: Literal["all","pending","approved_retain","approved_revoke"] = "all",
                        db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.get(PeriodicReviewCycle, cycle_id) is None:
        raise HTTPException(404,"Review cycle not found")
    query = db.query(PeriodicAccountReview).filter(PeriodicAccountReview.cycle_id==cycle_id)
    if user.role != 'admin':
        query=query.filter(PeriodicAccountReview.assigned_to==user.username)
    if state != 'all':
        query=query.filter(PeriodicAccountReview.state==state)
    total=query.count()
    tasks=query.order_by(PeriodicAccountReview.id).offset(offset).limit(limit).options(
        joinedload(PeriodicAccountReview.account).joinedload(Account.employee)).all()
    return {"total":total,"limit":limit,"offset":offset,"items":[account_task_dict(t) for t in tasks]}


@app.post("/api/review-cycles/accounts/{task_id}/decision")
def decide_cycle_account(task_id: int, body: DecideInput,
                         db: Session = Depends(get_db), user: User = Depends(current_user)):
    task=db.get(PeriodicAccountReview,task_id)
    if task is None:
        raise HTTPException(404,'Account review not found')
    if user.role != 'admin' and task.assigned_to != user.username:
        raise HTTPException(403,'Not assigned to you')
    if task.state != 'pending':
        raise HTTPException(409,'Review already decided')
    task.state='approved_revoke' if body.decision=='revoke' else 'approved_retain'
    task.remediation_state='awaiting_simulation' if body.decision=='revoke' else 'not_required'
    task.rationale=body.reason
    task.decided_by=user.username
    task.decided_at=utcnow()
    # Complete only transfers frozen as evidence for THIS review task, never
    # later transfers discovered after the cycle was created.
    transfer_ids = task.evidence_snapshot.get('pending_transfer_ids', [])
    if transfer_ids:
        account = db.get(Account, task.account_id)
        cycle = db.get(PeriodicReviewCycle, task.cycle_id)
        for event_id in transfer_ids:
            event = db.get(EmployeeTransfer, int(event_id))
            if not event or not account or account.employee_id != event.employee_id or event.occurred_at > cycle.window_end_at:
                raise HTTPException(409, 'Transfer evidence no longer matches this account/cycle')
            disposition = db.query(TransferAccessDisposition).filter_by(transfer_id=event.id,
                                                                           account_id=account.id).first()
            if disposition is None:
                db.add(TransferAccessDisposition(transfer_id=event.id, account_id=account.id,
                       cycle_id=cycle.id, decision=task.state, reviewed_by=user.username,
                       reviewed_at=task.decided_at, rationale=body.reason))
    audit(db,user.username,'PERIODIC_ACCOUNT_DECIDED' ,'account_review',task_id,
          {"cycle_id":task.cycle_id,"account_id":task.account_id,"decision":body.decision,"reason":body.reason})
    db.commit()
    return {"id":task_id,"state":task.state,"remediation_state":task.remediation_state,
            "upstream_changed":False}


@app.post("/api/review-cycles/accounts/{task_id}/simulate")
def simulate_cycle_account(task_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    task=db.get(PeriodicAccountReview,task_id)
    if task is None:
        raise HTTPException(404,'Account review not found')
    if task.state!='approved_revoke' or task.remediation_state!='awaiting_simulation':
        raise HTTPException(409,'Approved revocation required before simulation')
    task.remediation_state='simulated'
    audit(db,user.username,'PERIODIC_ACCOUNT_REVOCATION_SIMULATED','account_review',task_id,
          {"account_id":task.account_id,"upstream_changed":False,"verified":False})
    db.commit()
    return {"id":task_id,"remediation_state":'simulated',"upstream_changed":False,"verified":False}

@app.post("/api/reviews/create")
def create_reviews(body: CreateReviewInput, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    entitlements = db.query(Entitlement).options(joinedload(Entitlement.account).joinedload(Account.employee)).filter(Entitlement.active.is_(True), Entitlement.risk_level.in_(body.risk_levels)).all()
    existing = {r.entitlement_id for r in db.query(Review).filter(Review.state == "pending").all()}
    count = 0
    for ent in entitlements:
        if ent.id in existing:
            continue
        assigned = ent.account.employee.manager_username if ent.account.employee else "reviewer"
        reviewer_exists = db.query(User).filter_by(username=assigned).first()
        if not reviewer_exists:
            assigned = "reviewer"
        db.add(Review(entitlement_id=ent.id, assigned_to=assigned))
        count += 1
    audit(db, user.username, "REVIEWS_CREATED", "review", "batch", {"created": count, "risk_levels": body.risk_levels})
    db.commit()
    return {"created": count}

@app.post("/api/reviews/{review_id}/decision")
def decide_review(review_id: int, body: DecideInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Review not found")
    if user.role != "admin" and review.assigned_to != user.username:
        raise HTTPException(403, "Review is not assigned to you")
    if review.state != "pending":
        raise HTTPException(409, "Review is already decided")
    review.state = "approved_revoke" if body.decision == "revoke" else "approved_retain"
    review.remediation_state = "awaiting_simulation" if body.decision == "revoke" else "not_required"
    review.reason = body.reason
    review.decided_at = utcnow()
    review.decided_by = user.username
    audit(db, user.username, "REVIEW_DECIDED", "review", review_id, {"decision": body.decision, "rationale": body.reason})
    db.commit()
    return {"id": review.id, "state": review.state, "remediation_state": review.remediation_state}

@app.post("/api/reviews/{review_id}/simulate")
def simulate_remediation(review_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Review not found")
    if review.state != "approved_revoke" or review.remediation_state != "awaiting_simulation":
        raise HTTPException(409, "Requires an approved revocation not yet simulated")
    review.remediation_state = "simulated"
    review.remediation_at = utcnow()
    # Deliberately do NOT set Entitlement.active=False: real upstream access is unchanged.
    audit(db, user.username, "REVOCATION_SIMULATED", "review", review_id, {"upstream_changed": False, "verified": False, "entitlement_id": review.entitlement_id})
    db.commit()
    return {"id": review.id, "remediation_state": "simulated", "upstream_changed": False, "verified": False}

@app.get("/api/audit")
def audits(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return [{"id": a.id, "actor": a.actor, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "details": a.details, "created_at": a.created_at} for a in db.query(Audit).order_by(Audit.id.desc()).limit(limit).all()]

@app.get("/api/export/reviews.csv")
def export_reviews(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    # Prefix spreadsheet formula initiators to avoid CSV formula injection on export.
    def safe(v):
        s = str(v if v is not None else "")
        return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else s
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["review_id", "employee", "platform", "resource", "permission", "risk_score", "reviewer", "decision", "rationale", "remediation_state", "upstream_verified"])
    for r in db.query(Review).options(joinedload(Review.entitlement).joinedload(Entitlement.account).joinedload(Account.employee)).all():
        e = r.entitlement
        writer.writerow([safe(x) for x in [r.id, e.account.employee.name if e.account.employee else "Unmapped", e.account.platform, e.resource, e.permission, e.risk_score, r.decided_by or r.assigned_to, r.state, r.reason, r.remediation_state, False]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=access-review-evidence.csv", "Cache-Control": "no-store"})

@app.get("/api/review-cycles/{cycle_id}/export.csv")
def export_periodic_cycle(cycle_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Audit evidence for one account-level campaign; never claims upstream verification."""
    if db.get(PeriodicReviewCycle,cycle_id) is None:
        raise HTTPException(404,'Review cycle not found')
    def safe(value):
        result=str(value if value is not None else '')
        return "'"+result if result.lstrip().startswith(('=','+','-','@')) else result
    buf=io.StringIO()
    csv_writer=csv.writer(buf)
    csv_writer.writerow(['cycle_id','account_id','username','platform','employee','priority',
                         'policy_score','anomaly_percentile','assigned_to','decision',
                         'decision_reason','decided_by','decided_at','remediation_state',
                         'upstream_verified','review_reasons'])
    query=db.query(PeriodicAccountReview).filter(PeriodicAccountReview.cycle_id==cycle_id).options(
        joinedload(PeriodicAccountReview.account).joinedload(Account.employee))
    for task in query.yield_per(200):
        csv_writer.writerow([safe(v) for v in (cycle_id,task.account_id,task.account.username,
            task.account.platform,task.account.employee.name if task.account.employee else 'Unmapped',
            task.priority,task.policy_score,task.anomaly_percentile,task.assigned_to,
            task.state,task.rationale,task.decided_by,task.decided_at,
            task.remediation_state,False,'; '.join(task.evidence_snapshot.get('reasons',[])))])
    return StreamingResponse(iter([buf.getvalue()]),media_type='text/csv',
        headers={'Content-Disposition':f'attachment; filename=quarterly-cycle-{cycle_id}-evidence.csv',
                 'Cache-Control':'no-store'})

@app.get("/api/integrations/status")
def integration_status(user: User = Depends(current_user)):
    return {"github_configured": bool(os.getenv("GITHUB_ORG") and os.getenv("GITHUB_TOKEN")), "github_org": os.getenv("GITHUB_ORG", ""), "windows": "CSV import", "linux": "CSV import", "github": "Optional read-only REST sync", "remediation": "Simulation only"}

@app.post("/api/integrations/import/{dataset}")
async def upload_csv(dataset: Literal["employees", "accounts", "entitlements", "activities", "coverage"], file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(422, "Upload a CSV file")
    data = await file.read(2_000_001)
    count = import_csv(db, dataset, data)
    # A separate committed transaction records provenance after import completion.
    result = recompute(db)
    audit(db, user.username, "CSV_IMPORTED", dataset, "batch", {"records": count, "filename": os.path.basename(file.filename), "analyzed": result["analyzed"]})
    db.commit()
    return {"imported": count, "dataset": dataset}

@app.post("/api/integrations/github/sync")
async def github_sync(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    result = await sync_github(db)
    recompute(db)
    audit(db, user.username, "GITHUB_SYNC", "integration", "github", result)
    db.commit()
    return result
