"""AccessGuard Complete Research Lab — FastAPI backend.

IMPORTANT: Research prototype only.
- Uses synthetic/demo data by default.
- No authentication or RBAC. Bind to 127.0.0.1 ONLY.
- No real permissions are ever revoked. Remediation is simulated locally.
- Do NOT deploy on the public internet.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_session
from models import (
    Identity, System, Account, AccessGrant,
    Review, AuditLog, ActivityEvent, ConnectorRun, now_utc,
)
from risk import access_dict, risk_level

app = FastAPI(
    title='AccessGuard Complete Research Lab API',
    version='2.0.0',
    description='AI-powered user access governance research prototype.',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def access_rows(db: Session):
    return db.execute(
        select(AccessGrant, Account, Identity, System)
        .join(Account, AccessGrant.account_id == Account.id)
        .outerjoin(Identity, Account.identity_id == Identity.id)
        .join(System, Account.system_id == System.id)
        .order_by(AccessGrant.id.desc())
    ).all()


def grant_data(db: Session) -> list[dict]:
    return [
        access_dict(grant, account, identity, system)
        for grant, account, identity, system in access_rows(db)
    ]


def account_data(db: Session) -> list[dict]:
    rows = db.execute(
        select(Account, Identity, System)
        .outerjoin(Identity, Account.identity_id == Identity.id)
        .join(System, Account.system_id == System.id)
        .order_by(Account.id.desc())
    ).all()
    return [{
        'id': a.id,
        'identity_id': a.identity_id,
        'identity_name': i.name if i else None,
        'system_id': s.id,
        'system_name': s.name,
        'username': a.username,
        'external_account_id': a.external_account_id,
        'account_email': a.account_email,
        'status': a.status,
        'source': a.source,
        'mapping_method': a.mapping_method,
        'mapping_status': 'Linked' if a.identity_id is not None else 'Unlinked',
        'last_seen_at': a.last_seen_at.isoformat() if a.last_seen_at else None,
        'grants': db.scalar(
            select(func.count(AccessGrant.id)).where(AccessGrant.account_id == a.id)
        ) or 0,
    } for a, i, s in rows]


def _log(db: Session, actor: str, action: str, entity: str, details: str) -> None:
    db.add(AuditLog(
        created_at=now_utc(), actor=actor,
        action=action, entity=entity, details=details,
    ))


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get('/api/health')
def health(db: Session = Depends(get_session)):
    count = db.scalar(select(func.count(Identity.id)))
    return {
        'status': 'ok' if count is not None else 'error',
        'version': '2.0.0',
        'database': 'PostgreSQL',
        'identities': count or 0,
        'mode': 'synthetic-demo-only',
    }


# ─── Overview ─────────────────────────────────────────────────────────────────

@app.get('/api/overview')
def overview(db: Session = Depends(get_session)):
    persons = db.scalars(select(Identity)).all()
    grants = grant_data(db)
    active = [g for g in grants if g['grant_status'] == 'Active']
    risks = {
        name: sum(g['risk_level'] == name for g in active)
        for name in ['Critical', 'High', 'Medium', 'Low']
    }
    systems = db.scalars(select(System)).all()
    system_counts = [
        {'name': s.name, 'total': sum(g['system_id'] == s.id for g in active), 'id': s.id}
        for s in systems
    ]
    system_counts.sort(key=lambda r: r['total'], reverse=True)
    review_rows = db.scalars(select(Review)).all()
    review_stats = [
        {'status': status, 'total': sum(r.status == status for r in review_rows)}
        for status in ['Pending', 'Approved', 'Retained', 'Remediated']
        if any(r.status == status for r in review_rows)
    ]
    accounts_all = db.scalars(select(Account)).all()
    dept_risk: dict[str, dict] = defaultdict(lambda: {'total': 0, 'high': 0})
    for g in active:
        dept = g.get('department', 'Unknown')
        dept_risk[dept]['total'] += 1
        if g['risk_score'] >= 60:
            dept_risk[dept]['high'] += 1
    dept_breakdown = [
        {'department': d, 'total': v['total'], 'high_risk': v['high']}
        for d, v in sorted(dept_risk.items(), key=lambda x: x[1]['high'], reverse=True)
    ]
    return {
        'stats': {
            'identities': len(persons),
            'accounts': len(accounts_all),
            'linked_accounts': sum(a.identity_id is not None for a in accounts_all),
            'unlinked_accounts': sum(a.identity_id is None for a in accounts_all),
            'active_access': len(active),
            'high_risk': sum(g['risk_score'] >= 60 for g in active),
            'critical_risk': sum(g['risk_score'] >= 85 for g in active),
            'pending_reviews': sum(r.status == 'Pending' for r in review_rows),
            'systems': len(systems),
            'departed_access': sum(
                g['status'] == 'Departed' for g in active
            ),
            'review_completion': round(
                sum(r.status in ('Approved', 'Retained', 'Remediated') for r in review_rows)
                / max(1, len(review_rows)) * 100
            ),
        },
        'categories': [
            {'name': t, 'count': sum(p.type == t for p in persons)}
            for t in ['Human', 'Machine', 'Vendor']
        ],
        'systems': system_counts,
        'risks': risks,
        'dept_breakdown': dept_breakdown,
        'high_risks': sorted(
            [g for g in active if g['risk_score'] >= 60],
            key=lambda g: g['risk_score'],
            reverse=True,
        )[:8],
        'review_stats': review_stats,
    }


class CreateIdentityBody(BaseModel):
    id: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=255)
    department: str = Field(min_length=2, max_length=100)
    job_title: str = Field(min_length=2, max_length=120)
    type: str = Field(default='Human')
    status: str = Field(default='Active')
    manager: str = Field(default='Unassigned', max_length=120)


@app.post('/api/identities')
def create_identity(body: CreateIdentityBody, db: Session = Depends(get_session)):
    existing = db.get(Identity, body.id)
    if existing:
        raise HTTPException(409, f'Employee with ID "{body.id}" already exists')
    
    person = Identity(
        id=body.id.strip(),
        name=body.name.strip(),
        email=body.email.strip().lower(),
        department=body.department.strip(),
        job_title=body.job_title.strip(),
        type=body.type,
        status=body.status,
        manager=body.manager.strip() if body.manager else 'Unassigned',
    )
    db.add(person)
    try:
        db.flush()
        _log(db, 'Security Administrator', 'IDENTITY_CREATED', f'Identity #{person.id}',
             f'Registered new employee {person.name} ({person.email}) in department {person.department}')
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(400, f'Failed to create identity: {str(e)}')
    return {'ok': True, 'identity': {'id': person.id, 'name': person.name, 'email': person.email}}


class ConnectDeviceBody(BaseModel):
    identity_id: str = Field(min_length=2, max_length=32)
    system_id: str = Field(min_length=2, max_length=32)
    username: str = Field(min_length=1, max_length=255)
    external_account_id: str | None = None
    account_email: str | None = None
    permission: str = Field(default='User', max_length=80)
    resource: str = Field(default='Standard Workspace', max_length=255)
    privilege: int = Field(default=0)


@app.post('/api/identities/{identity_id}/connect-device')
def connect_device(identity_id: str, body: ConnectDeviceBody, db: Session = Depends(get_session)):
    person = db.get(Identity, identity_id)
    if not person:
        raise HTTPException(404, 'Employee not found')
    
    system = db.get(System, body.system_id)
    if not system:
        raise HTTPException(404, f'System {body.system_id} does not exist')
    
    ext_id = body.external_account_id or f"{body.system_id.lower()}-{body.username}"
    account = Account(
        identity_id=person.id,
        system_id=system.id,
        external_account_id=ext_id,
        username=body.username.strip(),
        account_email=body.account_email or person.email,
        status='Active',
        source='ManualRegistration',
        mapping_method='DirectDeviceConnection',
        created_at=now_utc(),
    )
    db.add(account)
    db.flush()

    grant = AccessGrant(
        account_id=account.id,
        permission=body.permission,
        resource=body.resource,
        privilege=body.privilege,
        cross_department=0,
        status='Active',
        last_verified_use=now_utc(),
    )
    db.add(grant)
    db.flush()

    _log(db, 'Security Administrator', 'DEVICE_ACCOUNT_CONNECTED', f'Account #{account.id}',
         f'Connected device/account {account.username} on {system.name} for employee {person.name} ({person.id})')
    db.commit()
    return {'ok': True, 'account_id': account.id, 'username': account.username, 'grant_id': grant.id}


@app.post('/api/system/reset-db')
def reset_database(db: Session = Depends(get_session)):
    """Clears all records to provide a clean state for live employee & device entry."""
    db.query(Review).delete()
    db.query(AccessGrant).delete()
    db.query(ActivityEvent).delete()
    db.query(AuditLog).delete()
    db.query(Account).delete()
    db.query(Identity).delete()
    db.query(ConnectorRun).delete()

    # Re-initialize basic enterprise systems if missing
    default_systems = [
        ('WIN', 'Windows Active Directory', 'Identity'),
        ('LIN', 'Linux Server Cluster', 'Infrastructure'),
        ('GH',  'GitHub Enterprise', 'Development'),
        ('VPN', 'Dialog Corporate VPN Gateway', 'Network'),
        ('AWS', 'AWS Cloud Environment', 'Cloud'),
    ]
    for sys_id, name, cat in default_systems:
        if not db.get(System, sys_id):
            db.add(System(id=sys_id, name=name, category=cat))

    _log(db, 'Security Administrator', 'DATABASE_PURGED', 'System DB',
         'All mock/demo identities and grants cleared. Initialized clean state.')
    db.commit()
    return {'ok': True, 'message': 'Database cleared successfully. Ready for fresh employee entry.'}


# ─── Identities ───────────────────────────────────────────────────────────────

@app.get('/api/identities')
def identities(db: Session = Depends(get_session)):
    all_ids = db.scalars(select(Identity).order_by(Identity.id)).all()
    result = []
    for person in all_ids:
        accounts = db.scalars(
            select(Account).where(Account.identity_id == person.id)
        ).all()
        ids = [a.id for a in accounts]
        grants = (
            db.scalars(
                select(AccessGrant).where(AccessGrant.account_id.in_(ids))
            ).all()
            if ids else []
        )
        active = [a for a in grants if a.status == 'Active']
        high_risk_count = sum(
            1 for g in active
            if g.privilege or g.cross_department
        )
        result.append({
            'id': person.id,
            'name': person.name,
            'email': person.email,
            'department': person.department,
            'job_title': person.job_title,
            'type': person.type,
            'status': person.status,
            'manager': person.manager,
            'accounts': len(accounts),
            'grants': len(grants),
            'active_grants': len(active),
            'connected_systems': len({a.system_id for a in accounts}),
            'high_risk_grants': high_risk_count,
        })
    return result


@app.get('/api/identities/{identity_id}')
def identity_detail(identity_id: str, db: Session = Depends(get_session)):
    person = db.get(Identity, identity_id)
    if person is None:
        raise HTTPException(404, 'Identity not found')
    accounts = db.scalars(
        select(Account).where(Account.identity_id == person.id)
    ).all()
    account_ids = [a.id for a in accounts]
    grants = (
        db.scalars(
            select(AccessGrant).where(AccessGrant.account_id.in_(account_ids))
        ).all()
        if account_ids else []
    )
    active_grants = [g for g in grants if g.status == 'Active']
    all_grants = grant_data(db)
    my_grants = [g for g in all_grants if g['identity_id'] == person.id]
    reviews = []
    for g in my_grants:
        r = db.scalar(select(Review).where(Review.grant_id == g['id']))
        if r:
            reviews.append({
                'review_id': r.id,
                'grant_id': r.grant_id,
                'status': r.status,
                'reviewer': r.reviewer,
                'decided_at': r.decided_at.isoformat() if r.decided_at else None,
            })
    activity = db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.account_id.in_(account_ids))
        .order_by(ActivityEvent.occurred_at.desc())
        .limit(20)
    ).all() if account_ids else []
    return {
        'id': person.id,
        'name': person.name,
        'email': person.email,
        'department': person.department,
        'job_title': person.job_title,
        'type': person.type,
        'status': person.status,
        'manager': person.manager,
        'accounts': len(accounts),
        'active_grants': len(active_grants),
        'grants': my_grants,
        'reviews': reviews,
        'recent_activity': [
            {
                'id': e.id,
                'occurred_at': e.occurred_at.isoformat(),
                'action': e.action,
                'outcome': e.outcome,
                'ip_address': e.ip_address,
            }
            for e in activity
        ],
    }


@app.get('/api/identities/{identity_id}/accounts')
def identity_accounts(identity_id: str, db: Session = Depends(get_session)):
    if db.get(Identity, identity_id) is None:
        raise HTTPException(404, 'Identity not found')
    return [a for a in account_data(db) if a['identity_id'] == identity_id]


# ─── Accounts ─────────────────────────────────────────────────────────────────

@app.get('/api/accounts')
def accounts(db: Session = Depends(get_session)):
    return account_data(db)


@app.get('/api/accounts/suggestions')
def suggestions(db: Session = Depends(get_session)):
    """Unverified candidate identity links — NEVER applied automatically."""
    all_identities = db.scalars(select(Identity)).all()
    by_email: dict[str, list] = {}
    for identity in all_identities:
        if identity.email:
            key = identity.email.strip().casefold()
            by_email.setdefault(key, []).append(identity)
    output = []
    for account in account_data(db):
        if account['identity_id'] is not None or not account['account_email']:
            continue
        possible = by_email.get(account['account_email'].strip().casefold(), [])
        if len(possible) == 1:
            output.append({
                'account_id': account['id'],
                'username': account['username'],
                'system_name': account['system_name'],
                'suggested_identity_id': possible[0].id,
                'suggested_identity_name': possible[0].name,
                'reason': 'Exact email text match — ownership NOT verified',
                'status': 'Candidate only — manual verification required',
            })
    return output


class AccountCreate(BaseModel):
    system_id: str = Field(min_length=1, max_length=32)
    external_account_id: str = Field(min_length=2, max_length=255)
    username: str = Field(min_length=2, max_length=255)
    account_email: str | None = Field(default=None, max_length=255)


@app.post('/api/accounts', status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_session)):
    if not db.get(System, body.system_id):
        raise HTTPException(404, 'System not found')
    a = Account(
        system_id=body.system_id,
        external_account_id=body.external_account_id,
        username=body.username,
        account_email=body.account_email,
        identity_id=None,
        status='Active',
        source='DemoManual',
        mapping_method=None,
        created_at=now_utc(),
    )
    db.add(a)
    try:
        db.flush()
        _log(db, 'Demo Operator', 'ACCOUNT_DISCOVERED', f'Account #{a.id}',
             f'Synthetic unlinked account in {body.system_id}; owner unverified')
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'External account identifier already exists in this system')
    return {'ok': True, 'account_id': a.id, 'mapping_status': 'Unlinked'}


class LinkBody(BaseModel):
    identity_id: str = Field(min_length=2, max_length=32)
    reviewer: str = Field(min_length=2, max_length=80)
    verification_note: str = Field(min_length=12, max_length=500)
    confirmed: bool


@app.post('/api/accounts/{account_id}/link')
def link_account(account_id: int, body: LinkBody, db: Session = Depends(get_session)):
    if not body.confirmed:
        raise HTTPException(422, 'Confirm that you verified ownership in demo records')
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, 'Account not found')
    if account.identity_id is not None:
        raise HTTPException(409, 'Already linked. Unlink first after reviewing evidence')
    identity = db.get(Identity, body.identity_id)
    if identity is None:
        raise HTTPException(404, 'Target identity not found')
    account.identity_id = identity.id
    account.mapping_method = 'ManualVerified'
    _log(db, body.reviewer, 'ACCOUNT_LINKED', f'Account #{account.id}',
         f'System={account.system_id}; identity={identity.id}; note={body.verification_note}')
    db.commit()
    return {'ok': True, 'account_id': account.id, 'identity_id': identity.id,
            'mapping_status': 'Linked'}


class UnlinkBody(BaseModel):
    reviewer: str = Field(min_length=2, max_length=80)
    reason: str = Field(min_length=12, max_length=500)
    confirmed: bool


@app.post('/api/accounts/{account_id}/unlink')
def unlink_account(account_id: int, body: UnlinkBody, db: Session = Depends(get_session)):
    if not body.confirmed:
        raise HTTPException(422, 'Explicit confirmation required')
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, 'Account not found')
    if account.identity_id is None:
        raise HTTPException(409, 'Account already unlinked')
    old = account.identity_id
    account.identity_id = None
    account.mapping_method = None
    _log(db, body.reviewer, 'ACCOUNT_UNLINKED', f'Account #{account.id}',
         f'Previous identity={old}; reason={body.reason}; permissions NOT revoked')
    db.commit()
    return {'ok': True, 'account_id': account.id, 'mapping_status': 'Unlinked'}


# ─── Access Grants ────────────────────────────────────────────────────────────

@app.get('/api/access')
def access(db: Session = Depends(get_session)):
    return grant_data(db)


# ─── Integrations ─────────────────────────────────────────────────────────────

@app.get('/api/integrations')
def integrations(db: Session = Depends(get_session)):
    systems = db.scalars(select(System).order_by(System.id)).all()
    result = []
    for s in systems:
        total = db.scalar(
            select(func.count(AccessGrant.id))
            .join(Account, AccessGrant.account_id == Account.id)
            .where(Account.system_id == s.id, AccessGrant.status == 'Active')
        ) or 0
        result.append({
            'id': s.id,
            'name': s.name,
            'category': s.category,
            'total_active_grants': total,
            'connection': 'Demo data',
            'sync': 'Not connected',
        })
    return result


# ─── Reviews ─────────────────────────────────────────────────────────────────

@app.get('/api/reviews')
def reviews(db: Session = Depends(get_session)):
    grants = {a['id']: a for a in grant_data(db)}
    rows = db.scalars(select(Review).order_by(Review.id.desc())).all()
    result = []
    for r in rows:
        item = grants.get(r.grant_id)
        if item is not None:
            result.append({
                **item,
                'review_id': r.id,
                'review_status': r.status,
                'reviewer': r.reviewer,
                'decided_at': r.decided_at.isoformat() if r.decided_at else None,
                'grant_id': r.grant_id,
            })
    priority = {'Pending': 0, 'Approved': 1, 'Retained': 2, 'Remediated': 3}
    return sorted(result, key=lambda x: (priority.get(x['review_status'], 9), -x['review_id']))


class DecisionBody(BaseModel):
    decision: str = Field(pattern='^(approve|retain)$')
    reviewer: str = Field(default='Demo Reviewer', min_length=2, max_length=80)


@app.post('/api/reviews/{review_id}/decision')
def decide(review_id: int, body: DecisionBody, db: Session = Depends(get_session)):
    row = db.get(Review, review_id)
    if row is None:
        raise HTTPException(404, 'Review not found')
    if row.status != 'Pending':
        raise HTTPException(409, 'Only pending reviews can be decided')
    next_status = 'Approved' if body.decision == 'approve' else 'Retained'
    row.status = next_status
    row.reviewer = body.reviewer
    row.decided_at = now_utc()
    _log(db, body.reviewer, f'REVIEW_{next_status.upper()}', f'Grant #{row.grant_id}',
         f'Review #{review_id}: {body.decision}')
    db.commit()
    return {'ok': True, 'review_status': next_status}


@app.post('/api/reviews/{review_id}/simulate-revoke')
def simulate_revoke(review_id: int, db: Session = Depends(get_session)):
    row = db.get(Review, review_id)
    if row is None:
        raise HTTPException(404, 'Review not found')
    if row.status != 'Approved':
        raise HTTPException(409, 'Approval required before simulated remediation')
    grant = db.get(AccessGrant, row.grant_id)
    if grant is None:
        raise HTTPException(404, 'Grant not found')
    if grant.status != 'Active':
        raise HTTPException(409, 'Grant is not active')
    grant.status = 'Revoked'
    row.status = 'Remediated'
    _log(db, 'Demo Simulator', 'SIMULATED_REVOKE', f'Grant #{row.grant_id}',
         'LOCAL database record only — NO external permission was changed')
    db.commit()
    return {'ok': True, 'mode': 'simulated', 'review_status': 'Remediated'}


@app.post('/api/reviews/generate')
def generate_reviews(db: Session = Depends(get_session)):
    """Idempotent policy campaign. Existing decisions are NOT overwritten."""
    grants = grant_data(db)
    existing = set(db.scalars(select(Review.grant_id)).all())
    requested = [
        r for r in grants
        if r['grant_status'] == 'Active'
        and (r['risk_score'] >= 60 or r.get('status') == 'Departed')
        and r['id'] not in existing
    ]
    for r in requested:
        db.add(Review(grant_id=r['id'], status='Pending'))
    _log(db, 'Demo Policy Engine', 'REVIEW_CAMPAIGN_CREATED', 'Risk review queue',
         f'Created {len(requested)} new reviews for high-risk or departed-owner access. '
         f'Existing decisions unchanged.')
    db.commit()
    return {'ok': True, 'created': len(requested),
            'message': 'Reviews created; no external access was modified'}


# ─── Audit ────────────────────────────────────────────────────────────────────

@app.get('/api/audit')
def audit(limit: int = Query(default=100, le=500), db: Session = Depends(get_session)):
    events = db.scalars(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    ).all()
    return [{
        'id': r.id,
        'created_at': r.created_at.isoformat(),
        'actor': r.actor,
        'action': r.action,
        'entity': r.entity,
        'details': r.details,
    } for r in events]


# ─── Offboarding ──────────────────────────────────────────────────────────────

@app.get('/api/offboarding')
def offboarding(db: Session = Depends(get_session)):
    leavers = db.scalars(
        select(Identity).where(Identity.status == 'Departed').order_by(Identity.id)
    ).all()
    result = []
    for p in leavers:
        account_ids = db.scalars(
            select(Account.id).where(Account.identity_id == p.id)
        ).all()
        active = (
            db.scalar(
                select(func.count(AccessGrant.id)).where(
                    AccessGrant.account_id.in_(account_ids),
                    AccessGrant.status == 'Active',
                )
            ) or 0
        ) if account_ids else 0
        result.append({
            'id': p.id,
            'name': p.name,
            'email': p.email,
            'department': p.department,
            'job_title': p.job_title,
            'type': p.type,
            'status': p.status,
            'manager': p.manager,
            'active_access': active,
        })
    return result


# ─── Activity ─────────────────────────────────────────────────────────────────

@app.get('/api/activity')
def activity(limit: int = Query(default=200, le=500), db: Session = Depends(get_session)):
    from activity import summarize_activity
    limit = max(1, min(limit, 500))
    events = db.scalars(
        select(ActivityEvent).order_by(ActivityEvent.occurred_at.desc()).limit(limit)
    ).all()
    account_ids = {e.account_id for e in events}
    accts = (
        {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(account_ids))).all()}
        if account_ids else {}
    )
    return summarize_activity(events, accts)


# ─── Alerts ───────────────────────────────────────────────────────────────────

@app.get('/api/alerts')
def alerts(db: Session = Depends(get_session)):
    rows = [a for a in grant_data(db) if a['grant_status'] == 'Active' and a['risk_score'] >= 60]
    return [{
        'id': r['id'],
        'identity_name': r['identity_name'],
        'system_name': r['system_name'],
        'permission': r['permission'],
        'risk_score': r['risk_score'],
        'risk_level': r['risk_level'],
        'explanation': r['reasons'],
        'department': r.get('department'),
        'status': 'Needs review',
    } for r in sorted(rows, key=lambda x: x['risk_score'], reverse=True)]


# ─── AI Summary & ML Microservice ─────────────────────────────────────────────

@app.get('/api/ai/summary')
def ai_summary(db: Session = Depends(get_session)):
    from ml_client import query_external_ml
    from ai_engine import rank_anomalies
    grants = grant_data(db)

    # 1. Try external Dialog-Project-Final-ML microservice
    ext_result = query_external_ml(grants)
    if ext_result is not None:
        return ext_result

    # 2. Seamless fallback to local IsolationForest engine
    local_result = rank_anomalies(grants)
    local_result['source'] = 'fallback-local-ml'
    return local_result


@app.get('/api/ml/status')
def ml_status():
    from ml_client import check_external_ml_health
    return check_external_ml_health()


@app.get('/api/ml/platforms')
def ml_platforms():
    from ml_client import load_platform_metadata
    return load_platform_metadata()


# ─── Dialog Access Log Service (Pasindu) ──────────────────────────────────────

@app.get('/api/accesslog/status')
def accesslog_status():
    from accesslog_client import check_accesslog_health
    return check_accesslog_health()


@app.get('/api/accesslog/summary')
def accesslog_summary():
    from accesslog_client import get_accesslog_summary
    return get_accesslog_summary()


@app.get('/api/accesslog/events')
def accesslog_events(limit: int = Query(50, ge=1, le=200), device: str = '', event_type: str = ''):
    from accesslog_client import get_accesslog_events
    return get_accesslog_events(limit=limit, device=device, event_type=event_type)


@app.get('/api/accesslog/devices')
def accesslog_devices():
    from accesslog_client import get_accesslog_devices
    return get_accesslog_devices()


@app.get('/api/accesslog/alerts')
def accesslog_alerts():
    from accesslog_client import get_accesslog_alerts
    return get_accesslog_alerts()


@app.post('/api/accesslog/sync')
def accesslog_sync(db: Session = Depends(get_session)):
    from accesslog_client import sync_accesslog_to_activity
    return sync_accesslog_to_activity(db)


# ─── FTP Connector (Dialog Access Log) ────────────────────────────────────────

@app.post('/api/connectors/ftp/sync')
def ftp_sync(db: Session = Depends(get_session)):
    from connectors.ftp_connector import sync_dialog_ftp
    import os
    host = os.getenv('FTP_HOST', '127.0.0.1')
    port = int(os.getenv('FTP_PORT', '21'))
    user = os.getenv('FTP_USER', 'dialog_access')
    password = os.getenv('FTP_PASS', '')
    remote_dir = os.getenv('FTP_DIR', '/incoming_logs')
    res = sync_dialog_ftp(db, host=host, port=port, user=user, password=password, remote_dir=remote_dir)
    return res


@app.get('/api/connectors/ftp/status')
def ftp_status(db: Session = Depends(get_session)):
    import os
    from pathlib import Path
    spool_dir = Path(__file__).resolve().parent / 'sample_imports' / 'ftp_spool'
    spool_files = [p.name for p in spool_dir.glob('*.csv')] if spool_dir.exists() else []
    runs = db.scalars(
        select(ConnectorRun).where(ConnectorRun.source == 'FTP:dialog-access-log')
        .order_by(ConnectorRun.id.desc()).limit(5)
    ).all()
    return {
        'host': os.getenv('FTP_HOST', '127.0.0.1'),
        'port': int(os.getenv('FTP_PORT', '21')),
        'user': os.getenv('FTP_USER', 'dialog_access'),
        'remote_dir': os.getenv('FTP_DIR', '/incoming_logs'),
        'spool_files_available': spool_files,
        'last_sync': runs[0].completed_at.isoformat() if runs and runs[0].completed_at else None,
        'last_status': runs[0].status if runs else 'Not yet synced',
    }


# ─── Metrics / Timeline ───────────────────────────────────────────────────────

@app.get('/api/metrics')
def metrics(db: Session = Depends(get_session)):
    """Aggregated KPIs for the dashboard metrics panel."""
    grants = grant_data(db)
    active = [g for g in grants if g['grant_status'] == 'Active']
    reviews_all = db.scalars(select(Review)).all()
    total_reviews = len(reviews_all)
    completed = sum(r.status in ('Approved', 'Retained', 'Remediated') for r in reviews_all)
    remediated = sum(r.status == 'Remediated' for r in reviews_all)
    pending = sum(r.status == 'Pending' for r in reviews_all)

    # Average risk score
    avg_risk = round(
        sum(g['risk_score'] for g in active) / max(1, len(active))
    )

    # Accounts
    all_accounts = db.scalars(select(Account)).all()
    unlinked = sum(a.identity_id is None for a in all_accounts)

    # Admin grants
    admin_grants = sum(g['privilege'] for g in active)

    # Cross-dept grants
    cross_grants = sum(g['cross_department'] for g in active)

    # Departed with active access
    departed_access = sum(g['status'] == 'Departed' for g in active)

    return {
        'avg_risk_score': avg_risk,
        'total_active_grants': len(active),
        'admin_grants': admin_grants,
        'cross_dept_grants': cross_grants,
        'unlinked_accounts': unlinked,
        'departed_with_access': departed_access,
        'total_reviews': total_reviews,
        'completed_reviews': completed,
        'remediated_grants': remediated,
        'pending_reviews': pending,
        'review_completion_pct': round(completed / max(1, total_reviews) * 100),
        'critical_grants': sum(g['risk_score'] >= 85 for g in active),
        'high_grants': sum(60 <= g['risk_score'] < 85 for g in active),
    }


@app.get('/api/stats/timeline')
def stats_timeline(days: int = Query(default=30, le=90), db: Session = Depends(get_session)):
    """Daily activity event counts for the last N days."""
    cutoff = _now() - timedelta(days=days)
    events = db.scalars(
        select(ActivityEvent).where(ActivityEvent.occurred_at >= cutoff)
    ).all()
    # Group by date
    by_date: dict[str, dict] = defaultdict(lambda: {'success': 0, 'failure': 0})
    for e in events:
        date_key = e.occurred_at.strftime('%Y-%m-%d')
        if e.outcome == 'Success':
            by_date[date_key]['success'] += 1
        else:
            by_date[date_key]['failure'] += 1
    # Fill gaps
    result = []
    for i in range(days):
        d = (_now() - timedelta(days=days - i - 1)).strftime('%Y-%m-%d')
        entry = by_date.get(d, {'success': 0, 'failure': 0})
        result.append({'date': d, **entry, 'total': entry['success'] + entry['failure']})
    return result


# ─── Reports ──────────────────────────────────────────────────────────────────

@app.get('/api/reports/summary')
def report_summary(db: Session = Depends(get_session)):
    summary = overview(db)
    activity_count = db.scalar(select(func.count(ActivityEvent.id))) or 0
    runs = db.scalars(
        select(ConnectorRun).order_by(ConnectorRun.id.desc()).limit(15)
    ).all()
    grants = grant_data(db)
    active = [g for g in grants if g['grant_status'] == 'Active']
    # Department breakdown
    dept_map: dict[str, dict] = defaultdict(lambda: {'total': 0, 'high': 0, 'admin': 0})
    for g in active:
        d = g.get('department', 'Unknown')
        dept_map[d]['total'] += 1
        if g['risk_score'] >= 60:
            dept_map[d]['high'] += 1
        if g.get('privilege'):
            dept_map[d]['admin'] += 1
    dept_breakdown = [
        {'department': d, **v}
        for d, v in sorted(dept_map.items(), key=lambda x: x[1]['high'], reverse=True)
    ]
    return {
        'generated_at': _now().isoformat(),
        'scope': 'Research prototype: synthetic and explicitly imported read-only snapshots',
        'metrics': summary['stats'],
        'risk_distribution': summary['risks'],
        'review_statuses': summary['review_stats'],
        'activity_events': activity_count,
        'dept_breakdown': dept_breakdown,
        'connector_runs': [{
            'id': r.id,
            'source': r.source,
            'status': r.status,
            'records_imported': r.records_imported,
            'completed_at': r.completed_at.isoformat() if r.completed_at else None,
            'details': r.details,
        } for r in runs],
        'caveats': [
            'No login/RBAC: bind to localhost only for research use',
            'All rules and anomaly scores are research illustrations, not security verdicts',
            'Simulation changes only local grant records; real permissions remain unchanged',
            'Unobserved activity does not prove non-use',
            'Isolation Forest is trained on synthetic cohort data only',
        ],
    }


# ─── Connector Runs ───────────────────────────────────────────────────────────

@app.get('/api/connectors/runs')
def connector_runs(db: Session = Depends(get_session)):
    runs = db.scalars(
        select(ConnectorRun).order_by(ConnectorRun.id.desc()).limit(40)
    ).all()
    return [{
        'id': r.id,
        'source': r.source,
        'status': r.status,
        'started_at': r.started_at.isoformat(),
        'completed_at': r.completed_at.isoformat() if r.completed_at else None,
        'records_imported': r.records_imported,
        'details': r.details,
    } for r in runs]
