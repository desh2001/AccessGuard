"""AccessGuard Complete Research Lab — FastAPI backend.

IMPORTANT: Research prototype only.
- Uses synthetic/demo data by default.
- No authentication or RBAC. Bind to 127.0.0.1 ONLY.
- No real permissions are ever revoked. Remediation is simulated locally.
- Do NOT deploy on the public internet.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from fastapi import Depends, FastAPI, HTTPException, Query, File, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, not_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_session
from models import (
    Identity, System, Account, AccessGrant,
    Review, AuditLog, ActivityEvent, ConnectorRun, now_utc,
    QuarterlyReviewCycle, QuarterlyAccountReview,
    ReviewOutcomeImportBatch, ReviewOutcomeImportRow,
    QuarterlyReviewOutcome, MLTrainingRun,
    ACCOUNT_TYPES, PLATFORM_NATIVE_ID_TYPES,
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


def access_rows(db: Session, env: str = 'production'):
    q = (
        select(AccessGrant, Account, Identity, System)
        .join(Account, AccessGrant.account_id == Account.id)
        .outerjoin(Identity, Account.identity_id == Identity.id)
        .join(System, Account.system_id == System.id)
    )
    if env == 'test':
        q = q.where(Account.source == 'EnterpriseSimulator')
    else:
        q = q.where(Account.source != 'EnterpriseSimulator')
    return db.execute(q.order_by(AccessGrant.id.desc())).all()


def grant_data(db: Session, env: str = 'production') -> list[dict]:
    return [
        access_dict(grant, account, identity, system)
        for grant, account, identity, system in access_rows(db, env=env)
    ]


def account_data(db: Session, env: str = 'production') -> list[dict]:
    q = (
        select(Account, Identity, System)
        .outerjoin(Identity, Account.identity_id == Identity.id)
        .join(System, Account.system_id == System.id)
    )
    if env == 'test':
        q = q.where(Account.source == 'EnterpriseSimulator')
    else:
        q = q.where(Account.source != 'EnterpriseSimulator')
    rows = db.execute(q.order_by(Account.id.desc())).all()
    return [{
        'id': a.id,
        'identity_id': a.identity_id,
        'identity_name': i.name if i else None,
        'system_id': s.id,
        'system_name': s.name,
        'username': a.username,
        'external_account_id': a.external_account_id,
        'account_type': a.account_type,
        'native_id': a.native_id,
        'native_id_type': a.native_id_type,
        'native_id_namespace': a.native_id_namespace,
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
def overview(env: str = Query('production'), db: Session = Depends(get_session)):
    if env == 'test':
        persons = db.scalars(select(Identity).where(Identity.id.like('sim-%'))).all()
        systems = db.scalars(select(System).where(System.id.like('SIM_%'))).all()
        accounts_all = db.scalars(select(Account).where(Account.source == 'EnterpriseSimulator')).all()
    else:
        persons = db.scalars(select(Identity).where(not_(Identity.id.like('sim-%')))).all()
        systems = db.scalars(select(System).where(not_(System.id.like('SIM_%')))).all()
        accounts_all = db.scalars(select(Account).where(Account.source != 'EnterpriseSimulator')).all()

    grants = grant_data(db, env=env)
    active = [g for g in grants if g['grant_status'] == 'Active']
    risks = {
        name: sum(g['risk_level'] == name for g in active)
        for name in ['Critical', 'High', 'Medium', 'Low']
    }
    system_counts = [
        {'name': s.name, 'total': sum(g['system_id'] == s.id for g in active), 'id': s.id}
        for s in systems
    ]
    system_counts.sort(key=lambda r: r['total'], reverse=True)
    active_grant_ids = {g['id'] for g in grants}
    review_rows = [
        r for r in db.scalars(select(Review)).all()
        if r.grant_id in active_grant_ids
    ]
    review_stats = [
        {'status': status, 'total': sum(r.status == status for r in review_rows)}
        for status in ['Pending', 'Approved', 'Retained', 'Remediated']
        if any(r.status == status for r in review_rows)
    ]
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
    account_type: str = Field(default='human', max_length=24)
    native_id: str | None = None
    native_id_type: str | None = None
    native_id_namespace: str | None = None
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

    act_type = (body.account_type or 'human').strip().lower()
    if act_type not in ACCOUNT_TYPES:
        raise HTTPException(422, f"Invalid account_type '{body.account_type}'. Must be one of {ACCOUNT_TYPES}")

    # Stable identifier validation: Never derive external ID from username/email!
    ext_id = (body.external_account_id or '').strip() or None
    native_id = (body.native_id or '').strip() or None
    native_id_type = (body.native_id_type or '').strip() or None
    native_id_namespace = (body.native_id_namespace or '').strip() or None

    has_any_native = any((native_id, native_id_type, native_id_namespace))
    has_full_native = all((native_id, native_id_type, native_id_namespace))

    if has_any_native and not has_full_native:
        raise HTTPException(422, 'Incomplete native ID tuple: native_id, native_id_type, and native_id_namespace are all required')

    if not ext_id:
        if has_full_native:
            ext_id = f"{native_id_type}:{native_id_namespace}:{native_id}"
        else:
            raise HTTPException(422, 'Must supply external_account_id or complete native ID tuple. Derivation from username/email is not permitted.')

    # Validate native_id_type against platform if system platform is defined
    if native_id_type and system.platform:
        allowed_types = PLATFORM_NATIVE_ID_TYPES.get(system.platform.lower().strip())
        if allowed_types and native_id_type not in allowed_types:
            raise HTTPException(422, f"native_id_type '{native_id_type}' is not valid for platform '{system.platform}'. Allowed: {sorted(allowed_types)}")

    account = Account(
        identity_id=person.id,
        system_id=system.id,
        external_account_id=ext_id,
        username=body.username.strip(),
        account_email=body.account_email or person.email,
        account_type=act_type,
        native_id=native_id,
        native_id_type=native_id_type,
        native_id_namespace=native_id_namespace,
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
    return {'ok': True, 'account_id': account.id, 'external_account_id': ext_id, 'account_type': act_type}
    db.commit()

    # Stream event to Sentinel Cloud Ingestion API
    try:
        from accesslog_client import forward_log_to_sentinel
        forward_log_to_sentinel(
            device_id=ext_id,
            username=account.username,
            event_type="LOGIN" if body.privilege == 0 else "PRIVILEGE",
            message=f"Device/Account {account.username} connected for employee {person.name} ({person.id}) with {body.permission} rights",
            ip="10.77.0.4"
        )
    except Exception:
        pass

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
def identities(env: str = Query('production'), db: Session = Depends(get_session)):
    q = select(Identity)
    if env == 'test':
        q = q.where(Identity.id.like('sim-%'))
    else:
        q = q.where(not_(Identity.id.like('sim-%')))
    all_ids = db.scalars(q.order_by(Identity.id)).all()
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
def accounts(env: str = Query('production'), db: Session = Depends(get_session)):
    return account_data(db, env=env)


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
    username: str = Field(min_length=1, max_length=255)
    account_type: str = Field(default='unknown', max_length=24)
    account_email: str | None = Field(default=None, max_length=255)
    native_id: str | None = None
    native_id_type: str | None = None
    native_id_namespace: str | None = None


@app.post('/api/accounts', status_code=201)
def create_account(body: AccountCreate, db: Session = Depends(get_session)):
    system = db.get(System, body.system_id)
    if not system:
        raise HTTPException(404, 'System not found')

    act_type = (body.account_type or 'unknown').strip().lower()
    if act_type not in ACCOUNT_TYPES:
        raise HTTPException(422, f"Invalid account_type '{body.account_type}'. Must be one of {ACCOUNT_TYPES}")

    native_id = (body.native_id or '').strip() or None
    native_id_type = (body.native_id_type or '').strip() or None
    native_id_namespace = (body.native_id_namespace or '').strip() or None

    has_any_native = any((native_id, native_id_type, native_id_namespace))
    has_full_native = all((native_id, native_id_type, native_id_namespace))

    if has_any_native and not has_full_native:
        raise HTTPException(422, 'Incomplete native ID tuple: native_id, native_id_type, and native_id_namespace are all required')

    if native_id_type and system.platform:
        allowed_types = PLATFORM_NATIVE_ID_TYPES.get(system.platform.lower().strip())
        if allowed_types and native_id_type not in allowed_types:
            raise HTTPException(422, f"native_id_type '{native_id_type}' is not valid for platform '{system.platform}'. Allowed: {sorted(allowed_types)}")

    a = Account(
        system_id=body.system_id,
        external_account_id=body.external_account_id.strip(),
        username=body.username.strip(),
        account_email=body.account_email.strip() if body.account_email else None,
        account_type=act_type,
        native_id=native_id,
        native_id_type=native_id_type,
        native_id_namespace=native_id_namespace,
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
        raise HTTPException(409, 'External account identifier or native ID tuple already exists in this system')
    return {'ok': True, 'account_id': a.id, 'mapping_status': 'Unlinked', 'account_type': act_type}


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
def access(env: str = Query('production'), db: Session = Depends(get_session)):
    return grant_data(db, env=env)


# ─── Integrations ─────────────────────────────────────────────────────────────

@app.get('/api/integrations')
def integrations(env: str = Query('production'), db: Session = Depends(get_session)):
    if env == 'test':
        systems = db.scalars(select(System).where(System.id.like('SIM_%')).order_by(System.id)).all()
    else:
        systems = db.scalars(select(System).where(not_(System.id.like('SIM_%'))).order_by(System.id)).all()
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
            'connection': 'Enterprise Simulator' if env == 'test' else 'Demo data',
            'sync': 'Connected' if env == 'test' else 'Not connected',
        })
    return result


# ─── Reviews ─────────────────────────────────────────────────────────────────

@app.get('/api/reviews')
def reviews(env: str = Query('production'), db: Session = Depends(get_session)):
    grants = {a['id']: a for a in grant_data(db, env=env)}
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

    account = db.get(Account, grant.account_id)
    if account and account.source == 'EnterpriseSimulator':
        # Route to Enterprise Simulator remediation engine
        from simulator_connector import remediate_simulator_grant
        # Extract company_id from external_account_id: sim-acc-{company_id}-{id}
        cid = 1
        try:
            parts = account.external_account_id.split('-')
            if len(parts) >= 3 and parts[2].isdigit():
                cid = int(parts[2])
        except Exception:
            cid = 1
        return remediate_simulator_grant(db, row, cid)

    grant.status = 'Revoked'
    row.status = 'Remediated'
    _log(db, 'Demo Simulator', 'SIMULATED_REVOKE', f'Grant #{row.grant_id}',
         'LOCAL database record only — NO external permission was changed')
    db.commit()
    return {'ok': True, 'mode': 'simulated', 'review_status': 'Remediated'}


@app.post('/api/reviews/generate')
def generate_reviews(env: str = Query('production'), db: Session = Depends(get_session)):
    """Idempotent policy campaign. Existing decisions are NOT overwritten."""
    grants = grant_data(db, env=env)
    existing = set(db.scalars(select(Review.grant_id)).all())
    requested = [
        r for r in grants
        if r['grant_status'] == 'Active'
        and (r['risk_score'] >= 60 or r.get('status') == 'Departed')
        and r['id'] not in existing
    ]
    for r in requested:
        db.add(Review(grant_id=r['id'], status='Pending'))
    _log(db, 'Access Review Engine', 'REVIEW_CAMPAIGN_CREATED', f'Risk review queue ({env})',
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
def offboarding(env: str = Query('production'), db: Session = Depends(get_session)):
    q = select(Identity).where(Identity.status == 'Departed')
    if env == 'test':
        q = q.where(Identity.id.like('sim-%'))
    else:
        q = q.where(not_(Identity.id.like('sim-%')))
    leavers = db.scalars(q.order_by(Identity.id)).all()
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
def activity(limit: int = Query(default=200, le=500), env: str = Query('production'), db: Session = Depends(get_session)):
    from activity import summarize_activity
    limit = max(1, min(limit, 500))
    q = select(ActivityEvent)
    if env == 'test':
        q = q.where(ActivityEvent.source == 'EnterpriseSimulator')
    else:
        q = q.where(ActivityEvent.source != 'EnterpriseSimulator')
    events = db.scalars(q.order_by(ActivityEvent.occurred_at.desc()).limit(limit)).all()
    account_ids = {e.account_id for e in events}
    accts = (
        {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(account_ids))).all()}
        if account_ids else {}
    )
    return summarize_activity(events, accts)


# ─── Alerts ───────────────────────────────────────────────────────────────────

@app.get('/api/alerts')
def alerts(env: str = Query('production'), db: Session = Depends(get_session)):
    rows = [a for a in grant_data(db, env=env) if a['grant_status'] == 'Active' and a['risk_score'] >= 60]
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
def ai_summary(env: str = Query('production'), db: Session = Depends(get_session)):
    """Legacy grant-level heuristic and baseline demo anomaly scoring.
    
    For live quarterly three-model access reviews, use /api/review-cycles.
    """
    from ai_engine import rank_anomalies
    grants = grant_data(db, env=env)
    local_result = rank_anomalies(grants)
    local_result['source'] = 'legacy-demo-rules'
    local_result['quarterly_v10_notice'] = (
        'Grant-level scoring is for legacy demonstration. '
        'Quarterly account-level reviews run via /api/review-cycles with Aegis V8/V9 platform models.'
    )
    return local_result


@app.get('/api/ml/status')
def ml_status():
    """Actual live health and loaded model status from the quarterly ML microservice."""
    from ml_client import check_ml_health
    return check_ml_health()


@app.get('/api/ml/platforms')
def ml_platforms():
    """Actual loaded platform models and real evaluation metadata from /v1/models."""
    from ml_client import get_ml_models
    return get_ml_models()


class UpdateSentinelTokenBody(BaseModel):
    token: str


@app.post('/api/sentinel/sync-now')
def sync_sentinel_now(db: Session = Depends(get_session)):
    """Pull all host logs from Sentinel VPS directly into AccessGuard Activity and Evidence DB."""
    from accesslog_client import sync_accesslog_to_activity
    res = sync_accesslog_to_activity(db)
    return res


@app.post('/api/sentinel/token')
def update_sentinel_token(body: UpdateSentinelTokenBody):
    import os
    os.environ['SENTINEL_INGESTION_TOKEN'] = body.token.strip()
    return {'ok': True, 'configured': bool(body.token.strip())}


@app.post('/api/sentinel/test-stream')
def test_stream_to_sentinel():
    from accesslog_client import forward_log_to_sentinel
    ok = forward_log_to_sentinel(
        device_id="WIN-DESKTOP-TEST",
        username="admin.test",
        event_type="LOGIN",
        message="Manual test event dispatched from AccessGuard UI to Sentinel VPS",
        ip="10.77.0.1"
    )
    return {'ok': ok}


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
def accesslog_events(limit: int = Query(100, ge=1, le=1000), device: str = '', event_type: str = '', source: str = ''):
    from accesslog_client import get_accesslog_events
    return get_accesslog_events(limit=limit, device=device, event_type=event_type, source=source)


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
def report_summary(env: str = Query('production'), db: Session = Depends(get_session)):
    summary = overview(env=env, db=db)
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


# ─── Quarterly Access Reviews & CSV Outcome Import (V10) ─────────────────────

class CyclePreviewBody(BaseModel):
    as_of: str | None = None
    window_days: int = 90
    budget_pct: int = 10
    cycle_id: str | None = None


class CycleCreateBody(BaseModel):
    as_of: str | None = None
    window_days: int = 90
    budget_pct: int = 10
    cycle_id: str | None = None
    created_by: str = 'Admin'


class AccountDecisionBody(BaseModel):
    decision: str
    reviewer_id: str
    rationale: str


class BatchCommitBody(BaseModel):
    approver: str = 'Review Administrator'


class PrepareTrainingBody(BaseModel):
    platform: str
    created_by: str = 'ML Admin'
    cycle_ids: list[str] | None = None


@app.post('/api/review-cycles/preview')
def preview_cycle(body: CyclePreviewBody, db: Session = Depends(get_session)):
    """Preview a quarterly 90-day review cycle without modifying database."""
    from quarterly_review_service import build_cycle_preview
    as_of_dt = None
    if body.as_of:
        try:
            as_of_dt = datetime.fromisoformat(body.as_of.replace('Z', '+00:00'))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid as_of timestamp format")

    try:
        preview = build_cycle_preview(
            db,
            as_of=as_of_dt,
            window_days=body.window_days,
            budget_pct=body.budget_pct,
            cycle_id=body.cycle_id,
        )
        return preview
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/api/review-cycles/create')
def create_cycle(body: CycleCreateBody, db: Session = Depends(get_session)):
    """Freeze and persist a quarterly review cycle and its account-level tasks."""
    from quarterly_review_service import create_review_cycle
    as_of_dt = None
    if body.as_of:
        try:
            as_of_dt = datetime.fromisoformat(body.as_of.replace('Z', '+00:00'))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid as_of timestamp format")

    try:
        cycle = create_review_cycle(
            db,
            as_of=as_of_dt,
            window_days=body.window_days,
            budget_pct=body.budget_pct,
            cycle_id=body.cycle_id,
            created_by=body.created_by,
        )
        return {
            'ok': True,
            'cycle_id': cycle.id,
            'status': cycle.status,
            'total_accounts': cycle.total_accounts,
            'mandatory_count': cycle.mandatory_count,
            'selected_count': cycle.selected_count,
            'deferred_count': cycle.deferred_count,
            'evidence_gap_count': cycle.evidence_gap_count,
            'mode': cycle.mode,
            'created_at': cycle.created_at.isoformat(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/review-cycles')
def list_review_cycles(db: Session = Depends(get_session)):
    """List all frozen quarterly review cycles with completion metrics."""
    cycles = db.scalars(
        select(QuarterlyReviewCycle).order_by(QuarterlyReviewCycle.created_at.desc())
    ).all()

    result = []
    for c in cycles:
        decided_count = db.scalar(
            select(func.count(QuarterlyAccountReview.id)).where(
                QuarterlyAccountReview.cycle_id == c.id,
                QuarterlyAccountReview.state == 'decided'
            )
        ) or 0
        total_tasks = db.scalar(
            select(func.count(QuarterlyAccountReview.id)).where(
                QuarterlyAccountReview.cycle_id == c.id,
                QuarterlyAccountReview.priority.in_(['mandatory', 'selected'])
            )
        ) or 0
        result.append({
            'id': c.id,
            'window_start': c.window_start.isoformat(),
            'window_end': c.window_end.isoformat(),
            'window_days': c.window_days,
            'review_budget_pct': c.review_budget_pct,
            'status': c.status,
            'mode': c.mode,
            'total_accounts': c.total_accounts,
            'mandatory_count': c.mandatory_count,
            'selected_count': c.selected_count,
            'deferred_count': c.deferred_count,
            'evidence_gap_count': c.evidence_gap_count,
            'created_by': c.created_by,
            'created_at': c.created_at.isoformat(),
            'queue_size': c.mandatory_count + c.selected_count,
            'decided_count': decided_count,
            'progress_pct': round((decided_count / total_tasks * 100), 1) if total_tasks > 0 else 0,
        })
    return result


@app.get('/api/review-cycles/{cycle_id}')
def get_cycle_detail(cycle_id: str, db: Session = Depends(get_session)):
    """Get single cycle metadata and overview."""
    c = db.get(QuarterlyReviewCycle, cycle_id)
    if not c:
        raise HTTPException(status_code=404, detail="Review cycle not found")

    decided_count = db.scalar(
        select(func.count(QuarterlyAccountReview.id)).where(
            QuarterlyAccountReview.cycle_id == c.id,
            QuarterlyAccountReview.state == 'decided'
        )
    ) or 0
    total_queue = db.scalar(
        select(func.count(QuarterlyAccountReview.id)).where(
            QuarterlyAccountReview.cycle_id == c.id,
            QuarterlyAccountReview.priority.in_(['mandatory', 'selected'])
        )
    ) or 0

    return {
        'id': c.id,
        'window_start': c.window_start.isoformat(),
        'window_end': c.window_end.isoformat(),
        'window_days': c.window_days,
        'review_budget_pct': c.review_budget_pct,
        'as_of': c.as_of.isoformat(),
        'status': c.status,
        'mode': c.mode,
        'total_accounts': c.total_accounts,
        'mandatory_count': c.mandatory_count,
        'selected_count': c.selected_count,
        'deferred_count': c.deferred_count,
        'evidence_gap_count': c.evidence_gap_count,
        'queue_size': total_queue,
        'decided_count': decided_count,
        'progress_pct': round((decided_count / total_queue * 100), 1) if total_queue > 0 else 0,
        'created_by': c.created_by,
        'created_at': c.created_at.isoformat(),
        'model_versions': json.loads(c.model_versions) if c.model_versions else {},
    }


@app.get('/api/review-cycles/{cycle_id}/accounts')
def list_cycle_accounts(
    cycle_id: str,
    priority: str | None = None,
    platform: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_session)
):
    """List account review tasks for a cycle with evidence and model details."""
    query = (
        select(QuarterlyAccountReview, Account, Identity)
        .join(Account, QuarterlyAccountReview.account_id == Account.id)
        .outerjoin(Identity, Account.identity_id == Identity.id)
        .where(QuarterlyAccountReview.cycle_id == cycle_id)
    )
    if priority and priority != 'all':
        query = query.where(QuarterlyAccountReview.priority == priority)
    if platform and platform != 'all':
        query = query.where(QuarterlyAccountReview.platform.ilike(f"%{platform}%"))
    if state and state != 'all':
        query = query.where(QuarterlyAccountReview.state == state)

    rows = db.execute(query.order_by(QuarterlyAccountReview.id.asc())).all()

    items = []
    for task, acc, ident in rows:
        reasons = []
        if task.policy_reasons:
            try:
                reasons = json.loads(task.policy_reasons)
            except Exception:
                reasons = [task.policy_reasons]

        items.append({
            'task_id': task.id,
            'account_id': acc.id,
            'external_account_id': acc.external_account_id,
            'username': acc.username,
            'account_type': acc.account_type,
            'native_id': acc.native_id,
            'native_id_type': acc.native_id_type,
            'native_id_namespace': acc.native_id_namespace,
            'identity_id': ident.id if ident else None,
            'identity_name': ident.name if ident else '[Unlinked Account]',
            'department': ident.department if ident else 'Unmapped',
            'job_title': ident.job_title if ident else 'N/A',
            'identity_status': ident.status if ident else 'Unmapped',
            'platform': task.platform,
            'priority': task.priority,
            'policy_score': task.policy_score,
            'policy_reasons': reasons,
            'ml_percentile': task.ml_percentile,
            'ml_status': task.ml_status,
            'ml_model_key': task.ml_model_key,
            'ml_model_schema': task.ml_model_schema,
            'ml_model_trained_utc': task.ml_model_trained_utc,
            'coverage_days': task.coverage_days,
            'coverage_known': bool(task.coverage_known),
            'transfer_flag': bool(task.transfer_flag),
            'state': task.state,
            'decision': task.decision,
            'decision_by': task.decision_by,
            'decision_at': task.decision_at.isoformat() if task.decision_at else None,
            'decision_rationale': task.decision_rationale,
        })
    return items


@app.post('/api/review-cycles/accounts/{task_id}/decision')
def submit_account_decision(
    task_id: int,
    body: AccountDecisionBody,
    db: Session = Depends(get_session)
):
    """Record authorized reviewer decision (retain, revoke-request, reduce-access-request)."""
    from quarterly_review_service import record_account_decision
    try:
        updated = record_account_decision(
            db,
            task_id=task_id,
            decision=body.decision,
            reviewer_id=body.reviewer_id,
            rationale=body.rationale,
        )
        return {
            'ok': True,
            'task_id': updated.id,
            'state': updated.state,
            'decision': updated.decision,
            'decision_by': updated.decision_by,
            'decision_at': updated.decision_at.isoformat() if updated.decision_at else None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/review-cycles/{cycle_id}/outcomes/template.csv')
def download_outcome_template(
    cycle_id: str,
    scope: str = 'review_queue',
    db: Session = Depends(get_session)
):
    """Download pre-populated CSV review template for a cycle."""
    from quarterly_review_service import generate_outcome_template_csv
    try:
        csv_str = generate_outcome_template_csv(db, cycle_id, scope=scope)
        filename = f"review_template_{cycle_id}_{scope}.csv"
        return Response(
            content=csv_str,
            media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post('/api/review-cycles/{cycle_id}/outcomes/import/preview')
async def preview_outcome_import(
    cycle_id: str,
    file: UploadFile = File(...),
    scope: str = 'full_population',
    uploader: str = 'Review Administrator',
    db: Session = Depends(get_session)
):
    """Preview uploaded review outcome CSV. Zero writes to final outcomes/models."""
    from quarterly_review_service import preview_outcome_csv
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only .csv files are supported on this endpoint")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(status_code=400, detail="File size exceeds maximum allowed 10MB")

    try:
        summary = preview_outcome_csv(
            db,
            cycle_id=cycle_id,
            file_bytes=content,
            original_filename=file.filename,
            uploader=uploader,
            scope=scope,
        )
        return summary
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/review-cycles/{cycle_id}/outcomes/import/{batch_id}')
def get_import_batch_status(cycle_id: str, batch_id: str, db: Session = Depends(get_session)):
    """Get staged batch status, counts and validation errors."""
    batch = db.get(ReviewOutcomeImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    rows = db.scalars(
        select(ReviewOutcomeImportRow).where(
            ReviewOutcomeImportRow.batch_id == batch_id,
            ReviewOutcomeImportRow.is_valid == 0
        ).limit(100)
    ).all()

    errors = [{
        'row_number': r.csv_row_number,
        'account_id': r.account_id,
        'code': r.error_code,
        'message': r.error_message,
    } for r in rows]

    return {
        'batch_id': batch.id,
        'cycle_id': batch.cycle_id,
        'original_filename': batch.original_filename,
        'file_sha256': batch.file_sha256,
        'status': batch.status,
        'total_rows': batch.total_rows,
        'valid_rows': batch.valid_rows,
        'invalid_rows': batch.invalid_rows,
        'duplicate_rows': batch.duplicate_rows,
        'can_commit': (batch.invalid_rows == 0 and batch.duplicate_rows == 0 and batch.status == 'previewed'),
        'errors': errors,
    }


@app.post('/api/review-cycles/{cycle_id}/outcomes/import/{batch_id}/commit')
def commit_outcome_import(
    cycle_id: str,
    batch_id: str,
    body: BatchCommitBody,
    db: Session = Depends(get_session)
):
    """Atomically commit all valid rows in a previewed batch into final outcomes."""
    from quarterly_review_service import commit_outcome_batch
    try:
        res = commit_outcome_batch(db, batch_id=batch_id, approver=body.approver)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/review-cycles/{cycle_id}/outcomes/export.csv')
def export_outcomes_csv(cycle_id: str, db: Session = Depends(get_session)):
    """Audit export of all accepted review outcomes with safe CSV escaping."""
    from quarterly_review_service import export_committed_outcomes_csv
    csv_str = export_committed_outcomes_csv(db, cycle_id)
    filename = f"review_outcomes_accepted_{cycle_id}.csv"
    return Response(
        content=csv_str,
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@app.get('/api/ml/training-readiness/{platform}')
def training_readiness(platform: str, db: Session = Depends(get_session)):
    """Inspect counts of approved review outcomes available for candidate offline training."""
    from quarterly_review_service import get_training_readiness
    return get_training_readiness(db, platform)


@app.post('/api/ml/training-runs/prepare')
def prepare_training_run(body: PrepareTrainingBody, db: Session = Depends(get_session)):
    """Prepare a frozen dataset snapshot record for offline model training."""
    from quarterly_review_service import prepare_training_candidate_snapshot
    try:
        run = prepare_training_candidate_snapshot(
            db,
            platform=body.platform,
            created_by=body.created_by,
            cycle_ids=body.cycle_ids,
        )
        return {
            'ok': True,
            'run_id': run.id,
            'platform': run.platform,
            'status': run.status,
            'training_normal_count': run.training_normal_count,
            'training_concern_count': run.training_concern_count,
            'created_at': run.created_at.isoformat(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/ml/training-runs')
def list_training_runs(db: Session = Depends(get_session)):
    """List model training snapshot runs."""
    runs = db.scalars(select(MLTrainingRun).order_by(MLTrainingRun.created_at.desc())).all()
    return [{
        'id': r.id,
        'platform': r.platform,
        'status': r.status,
        'model_schema': r.model_schema,
        'training_normal_count': r.training_normal_count,
        'training_concern_count': r.training_concern_count,
        'created_by': r.created_by,
        'created_at': r.created_at.isoformat(),
        'approved_by': r.approved_by,
        'promoted_at': r.promoted_at.isoformat() if r.promoted_at else None,
    } for r in runs]


# ═══════════════════════════════════════════════════════════════════════════
# TEST ENVIRONMENT / ENTERPRISE SIMULATOR BUILT-IN INTEGRATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

class SimulatorCompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    industry: str = 'Technology'
    count: int = Field(100, ge=1, le=100000)
    locations: str = 'Colombo'
    platforms: list[str] = ['github', 'aws', 'windows', 'linux']
    seed: int = 42
    start_hour: int = 8
    end_hour: int = 18
    speed: float = 60.0
    eps: int = 10
    active_pct: int = 80
    exception_pct: int = 2


@app.get('/api/simulator/health')
def simulator_health():
    """Verify connectivity with internal Enterprise Simulator service."""
    import httpx
    sim_url = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000')
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{sim_url}/api/health")
            if r.status_code == 200:
                return {'online': True, 'url': sim_url, **r.json()}
    except Exception as ex:
        return {'online': False, 'url': sim_url, 'error': str(ex)}
    return {'online': False, 'url': sim_url}


@app.get('/api/simulator/companies')
def simulator_list_companies():
    """Proxy list of virtual companies in Enterprise Simulator."""
    import httpx
    sim_url = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000')
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{sim_url}/api/companies")
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@app.post('/api/simulator/companies')
def simulator_create_company(body: SimulatorCompanyCreate, db: Session = Depends(get_session)):
    """One-click setup: Create company in simulator, generate virtual infrastructure, auto-sync to AccessGuard."""
    import httpx
    from simulator_connector import sync_company_inventory
    sim_url = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000')
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{sim_url}/api/companies", json=body.model_dump())
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"Failed to create company: {r.text}")
        co = r.json()
        cid = co['id']
        # Automatically start the simulation
        client.post(f"{sim_url}/api/companies/{cid}/simulation/start")

    # Auto-sync inventory into AccessGuard Test Environment
    sync_res = sync_company_inventory(db, cid)
    return {
        'ok': True,
        'company': co,
        'sync': sync_res,
        'message': f"Created virtual company '{body.name}' ({body.count} employees) and synchronized into AccessGuard Test Environment."
    }


@app.get('/api/simulator/companies/{company_id}/summary')
def simulator_company_summary(company_id: int):
    """Get live simulation stats from simulator backend."""
    import httpx
    sim_url = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000')
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{sim_url}/api/companies/{company_id}/summary")
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@app.get('/api/simulator/companies/{company_id}/collection')
def simulator_company_collection(
    company_id: int,
    table: str = Query('employees'),
    offset: int = 0,
    limit: int = 50,
    q: str = '',
    platform: str = '',
):
    """Proxy entity collection querying (employees, resources, accounts, grants, events)."""
    import httpx
    sim_url = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000')
    with httpx.Client(timeout=10.0) as client:
        r = client.get(
            f"{sim_url}/api/companies/{company_id}/{table}",
            params={'offset': offset, 'limit': limit, 'q': q, 'platform': platform}
        )
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@app.post('/api/simulator/companies/{company_id}/simulation/{action}')
def simulator_control_simulation(company_id: int, action: str):
    """Control simulation engine (start, pause, resume, stop, reset)."""
    import httpx
    sim_url = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000')
    with httpx.Client(timeout=5.0) as client:
        r = client.post(f"{sim_url}/api/companies/{company_id}/simulation/{action}")
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        return r.json()


@app.post('/api/simulator/companies/{company_id}/sync')
def simulator_sync_now(company_id: int, db: Session = Depends(get_session)):
    """Trigger on-demand full synchronization of simulator company into AccessGuard."""
    from simulator_connector import sync_company_inventory
    try:
        return sync_company_inventory(db, company_id)
    except Exception as ex:
        raise HTTPException(500, f"Sync failed: {str(ex)}")


@app.post('/api/simulator/companies/{company_id}/poll-events')
def simulator_poll_events(company_id: int, db: Session = Depends(get_session)):
    """Poll latest activity logs from simulator stream into AccessGuard database."""
    from simulator_connector import poll_and_ingest_live_events
    return poll_and_ingest_live_events(db, company_id)


@app.get('/api/simulator/scenarios')
def simulator_list_scenarios():
    """List available automated security test scenarios."""
    from simulator_connector import SCENARIOS_CATALOG
    return SCENARIOS_CATALOG


@app.post('/api/simulator/companies/{company_id}/scenarios/{scenario_id}/run')
def simulator_run_scenario(company_id: int, scenario_id: str, db: Session = Depends(get_session)):
    """Run predefined automated attack or governance test scenario."""
    from simulator_connector import execute_test_scenario
    try:
        return execute_test_scenario(db, company_id, scenario_id)
    except Exception as ex:
        raise HTTPException(400, f"Scenario execution failed: {str(ex)}")


@app.get('/api/simulator/companies/{company_id}/ml-metrics')
def simulator_ml_metrics(company_id: int, db: Session = Depends(get_session)):
    """Retrieve actual ML test evaluation metrics (Precision, Recall, F1, Latency)."""
    from simulator_connector import calculate_ml_test_metrics
    return calculate_ml_test_metrics(db, company_id)


@app.post('/api/simulator/companies/{company_id}/reset')
def simulator_reset_env(company_id: int, db: Session = Depends(get_session)):
    """Reset virtual company state and AccessGuard test environment completely."""
    from simulator_connector import reset_simulator_environment
    return reset_simulator_environment(db, company_id)


@app.delete('/api/simulator/companies/{company_id}')
def simulator_delete_company(company_id: int, db: Session = Depends(get_session)):
    """Permanently delete a virtual company and its simulated data."""
    from simulator_connector import delete_simulator_company
    return delete_simulator_company(db, company_id)


@app.post('/api/simulator/purge-all')
def simulator_purge_all(db: Session = Depends(get_session)):
    """Wipe ALL simulated data across all virtual companies from AccessGuard."""
    from simulator_connector import purge_all_simulator_data
    return purge_all_simulator_data(db)


# ─── Automated Admin Email Alert Settings ─────────────────────────────────────

class EmailSettingsUpdateBody(BaseModel):
    admin_name: str = Field(default='Main Security Administrator', min_length=2, max_length=120)
    admin_email: str = Field(min_length=5, max_length=255)
    enabled: bool = True
    smtp_host: str = Field(default='smtp.gmail.com', max_length=120)
    smtp_port: int = Field(default=587)
    smtp_user: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    sender_name: str = Field(default='AccessGuard Security Sentinel', max_length=120)
    notify_on_high_risk: bool = True
    notify_on_attack_detected: bool = True
    notify_on_reviews_queued: bool = True


@app.get('/api/settings/email')
def get_email_settings(db: Session = Depends(get_session)):
    """Get current admin email notification configuration."""
    from email_service import get_or_create_email_settings
    s = get_or_create_email_settings(db)
    return {
        'admin_name': s.admin_name,
        'admin_email': s.admin_email,
        'enabled': bool(s.enabled),
        'smtp_host': s.smtp_host,
        'smtp_port': s.smtp_port,
        'smtp_user': s.smtp_user or '',
        'has_password': bool(s.smtp_password),
        'sender_name': s.sender_name,
        'notify_on_high_risk': bool(s.notify_on_high_risk),
        'notify_on_attack_detected': bool(s.notify_on_attack_detected),
        'notify_on_reviews_queued': bool(s.notify_on_reviews_queued),
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
    }


@app.put('/api/settings/email')
def update_email_settings(body: EmailSettingsUpdateBody, db: Session = Depends(get_session)):
    """Update admin email notification configuration."""
    from email_service import get_or_create_email_settings
    s = get_or_create_email_settings(db)
    s.admin_name = body.admin_name.strip()
    s.admin_email = body.admin_email.strip().lower()
    s.enabled = 1 if body.enabled else 0
    s.smtp_host = body.smtp_host.strip()
    s.smtp_port = body.smtp_port
    s.smtp_user = body.smtp_user.strip() if body.smtp_user else None
    if body.smtp_password is not None and body.smtp_password != '':
        s.smtp_password = body.smtp_password.strip()
    s.sender_name = body.sender_name.strip()
    s.notify_on_high_risk = 1 if body.notify_on_high_risk else 0
    s.notify_on_attack_detected = 1 if body.notify_on_attack_detected else 0
    s.notify_on_reviews_queued = 1 if body.notify_on_reviews_queued else 0
    s.updated_at = now_utc()
    _log(db, 'Security Administrator', 'EMAIL_SETTINGS_UPDATED', s.admin_email,
         f"Admin email alerts routed to {s.admin_email} via {s.smtp_host}:{s.smtp_port}")
    db.commit()
    return {'ok': True, 'message': 'Admin email settings updated successfully.'}


class SendTestEmailBody(BaseModel):
    recipient: str | None = None


@app.post('/api/settings/email/test')
def send_test_email(body: SendTestEmailBody, db: Session = Depends(get_session)):
    """Send an immediate test security notification email to verify Gmail SMTP configuration."""
    from email_service import send_security_alert_email, get_or_create_email_settings
    s = get_or_create_email_settings(db)
    target = body.recipient or s.admin_email

    subject = "🔔 [TEST] AccessGuard Real Email Notification Verification"
    html_b = f"""<div style="font-family:sans-serif;padding:20px;border-radius:10px;background:#f9fafb;border:1px solid #e5e7eb;">
        <h2 style="color:#4f46e5;margin-top:0;">AccessGuard Automated Alert Test</h2>
        <p>This email confirms that <b>AccessGuard Real Gmail SMTP</b> automated notifications are properly configured.</p>
        <p><b>Target Admin:</b> {s.admin_name} ({target})</p>
        <p><b>SMTP Server:</b> {s.smtp_host}:{s.smtp_port}</p>
        <p style="color:#059669;font-weight:bold;">✓ Connection verified successfully.</p>
    </div>"""
    txt_b = f"AccessGuard Alert Test: Gmail SMTP verified for {s.admin_name} ({target})."

    res = send_security_alert_email(
        db=db,
        subject=subject,
        html_content=html_b,
        text_content=txt_b,
        trigger_type='test',
        recipient_override=target
    )
    return res


@app.get('/api/settings/email/logs')
def get_email_logs(limit: int = 50, db: Session = Depends(get_session)):
    """Retrieve history of dispatched security alert emails."""
    from models import EmailAlertLog
    logs = db.scalars(select(EmailAlertLog).order_by(EmailAlertLog.id.desc()).limit(limit)).all()
    return [{
        'id': l.id,
        'recipient': l.recipient,
        'subject': l.subject,
        'body': l.body,
        'status': l.status,
        'error_message': l.error_message,
        'trigger_type': l.trigger_type,
        'sent_at': l.sent_at.isoformat() if l.sent_at else None,
    } for l in logs]


