"""Enhanced seed — richer synthetic data for all 7 modules.

Creates identities, accounts, grants, reviews, activity events, and audit
records. All data is fictional. Never used on real production systems.
"""
from __future__ import annotations
import random
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import (
    Identity, System, Account, AccessGrant, Review,
    AuditLog, ActivityEvent, ConnectorRun, now_utc
)
from risk import calculate_risk

SYSTEMS = [
    ('GH',  'GitHub',           'Development'),
    ('LIN', 'Linux Servers',    'Infrastructure'),
    ('WIN', 'Windows AD',       'Identity'),
    ('AWS', 'AWS Cloud',        'Cloud'),
    ('SLK', 'Slack',            'Collaboration'),
    ('JRA', 'Jira',             'Project Management'),
    ('PG',  'PostgreSQL DB',    'Data'),
    ('CRM', 'Salesforce CRM',   'Business'),
    ('NTO', 'Notion',           'Collaboration'),
    ('ZOM', 'Zoom',             'Collaboration'),
    ('GRA', 'Grafana',          'Monitoring'),
    ('GCL', 'Google Cloud',     'Cloud'),
    ('SNW', 'Snowflake DW',     'Data'),
    ('K8S', 'Kubernetes',       'Infrastructure'),
]

GIVEN = [
    'Nethmi','Kasun','Isuri','Tharindu','Sachini','Dulanjali','Kavindu',
    'Dinuka','Hasini','Pasindu','Dilshan','Shanika','Ravindu','Pavithra',
    'Shehan','Sanduni','Amaya','Ruchira','Nimasha','Deshani','Sachintha',
    'Chathura','Imasha','Chamodi','Anjana','Minoli','Thilina','Rashmi',
    'Nipun','Lahiru','Senuri','Gayan','Vidusha','Vihanga','Janani',
    'Nimesh','Kaushalya','Dineth','Chamara','Pramudi','Yasiru','Vishwa',
    'Hiruni','Supun','Malsha','Chanuka','Ridma','Hasara','Daham','Sithara',
]
LAST = [
    'Perera','Fernando','Jayasinghe','Silva','Karunarathne','Wijesinghe',
    'Bandara','Samarasinghe','Dissanayake','Herath','Gunawardena','Rajapaksha',
    'Wickramasinghe','Liyanage','Madushanka',
]
DEPARTMENTS = ['Engineering','Finance','HR','Marketing','Operations','Sales','Legal']
TITLES = {
    'Engineering': 'Software Engineer',
    'Finance': 'Financial Analyst',
    'HR': 'HR Executive',
    'Marketing': 'Marketing Associate',
    'Operations': 'Operations Specialist',
    'Sales': 'Sales Executive',
    'Legal': 'Legal Counsel',
}
MANAGERS = [
    'Alex Morgan','Jamie Chen','Sam Okonkwo','Taylor Reyes','Jordan Patel',
]
ACTIONS = [
    'Login','Repository access','Database query','SSH session',
    'File read','API call','Password change','Permission check',
    'Report export','Configuration update',
]

# Departed employees (by sequential index 1-based)
DEPARTED = {8, 19, 31, 38, 47}

# Employees with deliberately interesting cross-dept access scenarios
FINANCE_IN_DEV = {3, 7, 15}  # Finance employees with Dev system access


def seed_demo(session: Session) -> bool:
    if session.scalar(select(Identity.id).limit(1)) is not None:
        return False

    rng = random.Random(42)

    # ── Systems ──────────────────────────────────────────────────────────────
    for id_, name, category in SYSTEMS:
        session.add(System(id=id_, name=name, category=category))
    session.flush()

    identities: list[Identity] = []

    # ── Human identities (1–55) ───────────────────────────────────────────────
    for i in range(1, 56):
        dep = rng.choice(DEPARTMENTS)
        name = f'{GIVEN[(i - 1) % len(GIVEN)]} {rng.choice(LAST)}'
        status = 'Departed' if i in DEPARTED else 'Active'
        identity = Identity(
            id=f'EMP-{i:04d}',
            name=name,
            email=f'identity{i:03d}@demo.example',
            department=dep,
            job_title=TITLES.get(dep, 'Staff'),
            type='Human',
            status=status,
            manager=rng.choice(MANAGERS),
        )
        identities.append(identity)
        session.add(identity)

    # ── Machine accounts (56–68) ──────────────────────────────────────────────
    for i in range(56, 69):
        identity = Identity(
            id=f'EMP-{i:04d}',
            name=f'svc-{i - 55:02d}',
            email=f'svc{i - 55:02d}@systems.demo.example',
            department='IT Services',
            job_title='Service Account',
            type='Machine',
            status='Active',
            manager='System Automation',
        )
        identities.append(identity)
        session.add(identity)

    # ── Vendor / contractor identities (69–74) ────────────────────────────────
    for i in range(69, 75):
        identity = Identity(
            id=f'EMP-{i:04d}',
            name=f'External Contractor {i - 68:02d}',
            email=f'contractor{i - 68:02d}@external.demo.example',
            department='External',
            job_title='Contractor',
            type='Vendor',
            status='Active',
            manager='Procurement',
        )
        identities.append(identity)
        session.add(identity)

    session.flush()

    high_risk_grants: list[int] = []  # grant ids for initial review seeding

    # ── Accounts + grants per identity ──────────────────────────────────────
    for identity in identities:
        n_systems = (
            rng.randint(2, 6) if identity.type == 'Human'
            else rng.randint(1, 4)
        )
        chosen_systems = rng.sample(SYSTEMS, min(n_systems, len(SYSTEMS)))

        for sys_id, sys_name, _ in chosen_systems:
            # For Finance employees, force some to have Dev/Infra access
            emp_num = int(identity.id.split('-')[1])
            is_cross = (
                identity.department == 'Finance'
                and sys_id in ('GH', 'LIN', 'PG', 'K8S')
                and emp_num in FINANCE_IN_DEV
            )

            account = Account(
                identity_id=identity.id,
                system_id=sys_id,
                external_account_id=f'demo:{sys_id.lower()}:{identity.id.lower()}',
                username=f'{identity.id.lower()}_{sys_id.lower()}',
                account_email=identity.email,
                status='Active',
                source='DemoSeed',
                mapping_method='DemoSeed',
                last_seen_at=now_utc() - timedelta(days=rng.randrange(1, 50)),
            )
            session.add(account)
            session.flush()

            perm = rng.choices(['Viewer', 'Editor', 'Admin'], weights=[50, 32, 18])[0]
            # Deliberately give departed users Admin in some cases
            if identity.status == 'Departed' and rng.random() < 0.5:
                perm = 'Admin'

            priv = int(perm == 'Admin')
            cross = int(is_cross and perm in ('Admin', 'Editor'))
            days_ago = rng.choice([1, 3, 7, 14, 21, 30, 45, 60, 75, 90, 110, 135, 160, 200])
            last_used = None if rng.random() < 0.10 else now_utc() - timedelta(days=days_ago)

            grant = AccessGrant(
                account_id=account.id,
                permission=perm,
                resource=f'{sys_name} / Workspace',
                privilege=priv,
                cross_department=cross,
                last_verified_use=last_used,
                status='Active',
            )
            session.add(grant)
            session.flush()

            score, _ = calculate_risk({
                'identity_id': identity.id,
                'status': identity.status,
                'privilege': priv,
                'cross_department': cross,
                'last_verified_use': last_used,
            })
            if score >= 60:
                high_risk_grants.append(grant.id)

    # ── Deliberately UNLINKED accounts (identity resolution exercise) ─────────
    for idx, (sys_id, sys_name, _) in enumerate(SYSTEMS[:5], start=1):
        email = (
            f'identity{idx:03d}@demo.example' if idx <= 2
            else f'unknown{idx}@external.demo.example'
        )
        orphan = Account(
            identity_id=None,
            system_id=sys_id,
            external_account_id=f'unknown:{sys_id}:{idx}',
            username=f'unmapped_{idx:02d}',
            account_email=email,
            status='Active',
            source='DemoSeed',
            mapping_method=None,
            last_seen_at=now_utc() - timedelta(days=120),
        )
        session.add(orphan)
        session.flush()

        perm = 'Admin' if idx == 1 else ('Editor' if idx == 3 else 'Viewer')
        orphan_grant = AccessGrant(
            account_id=orphan.id,
            permission=perm,
            resource=f'{sys_name} / Lab',
            privilege=int(perm == 'Admin'),
            cross_department=0,
            last_verified_use=None,
            status='Active',
        )
        session.add(orphan_grant)
        session.flush()
        if idx <= 2:
            high_risk_grants.append(orphan_grant.id)

    # ── Seed reviews for high-risk grants ─────────────────────────────────────
    for gid in high_risk_grants:
        session.add(Review(grant_id=gid, status='Pending'))

    # ── Activity events ───────────────────────────────────────────────────────
    all_accounts = session.scalars(
        select(Account).order_by(Account.id).limit(120)
    ).all()

    for idx, acct in enumerate(all_accounts):
        n_events = rng.randrange(2, 9)
        failure_prone = idx % 11 == 0

        for j in range(n_events):
            is_failure = (failure_prone and j < 5) or rng.random() < 0.08
            session.add(ActivityEvent(
                account_id=acct.id,
                occurred_at=now_utc() - timedelta(
                    days=rng.randrange(1, 90),
                    hours=rng.randrange(0, 24),
                ),
                action=rng.choice(ACTIONS),
                outcome='Failure' if is_failure else 'Success',
                ip_address=f'192.0.2.{rng.randrange(1, 254)}',
                source='DemoSeed',
            ))

    # ── Connector run provenance ──────────────────────────────────────────────
    session.add(ConnectorRun(
        source='DemoSeed',
        started_at=now_utc(),
        completed_at=now_utc(),
        status='Success',
        records_imported=len(all_accounts),
        details='Synthetic research data generator — no external systems connected.',
    ))

    # ── Bootstrap audit log ───────────────────────────────────────────────────
    session.add(AuditLog(
        created_at=now_utc(),
        actor='System',
        action='DEMO_SEEDED',
        entity='Research Lab',
        details=(
            f'Generated {len(identities)} synthetic identities, '
            f'{len(SYSTEMS)} systems, '
            f'{len(high_risk_grants)} initial high-risk reviews.'
        ),
    ))

    session.commit()
    return True


if __name__ == '__main__':
    from database import SessionLocal
    with SessionLocal() as s:
        result = seed_demo(s)
        print('Seeded.' if result else 'Already seeded — no changes made.')
