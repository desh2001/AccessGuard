"""One-time Phase1 SQLite -> Phase2 PostgreSQL importer.

Run after `alembic upgrade head` BEFORE seed_demo. Read-only SQLite input.
Never changes or deletes the existing Phase1 sqlite file.
"""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path
from sqlalchemy import select, text
from database import SessionLocal
from models import Identity, System, Account, AccessGrant, Review, AuditLog, now_utc
from risk import parse_time


def rows(conn, table):
    return [dict(x) for x in conn.execute(f'SELECT * FROM {table}')]


def run(filename: Path):
    if not filename.is_file():
        raise SystemExit(f'No SQLite file at {filename}')
    source=sqlite3.connect(f'file:{filename.resolve().as_posix()}?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    try:
        original={name:rows(source,name) for name in
            ('identities','systems','access_grants','reviews','audit_logs')}
    finally:
        source.close()
    with SessionLocal() as session:
        if session.scalar(select(Identity.id).limit(1)) is not None:
            raise SystemExit('Target database already contains identities. Use a NEW empty PostgreSQL database to import.')
        for x in original['identities']:
            session.add(Identity(**x))
        for x in original['systems']:
            session.add(System(**x))
        session.flush()
        account_map={}
        for g in original['access_grants']:
            key=(g['identity_id'],g['system_id'])
            if key not in account_map:
                ident=next(x for x in original['identities'] if x['id']==g['identity_id'])
                account=Account(identity_id=g['identity_id'], system_id=g['system_id'],
                    external_account_id=f'phase1:{g["system_id"].lower()}:{g["identity_id"].lower()}',
                    username=f'{g["identity_id"].lower()}_{g["system_id"].lower()}',
                    account_email=ident['email'],status='Active',source='Phase1Import',
                    mapping_method='HistoricalPhase1',last_seen_at=None,created_at=now_utc())
                session.add(account)
                session.flush()
                account_map[key]=account.id
            session.add(AccessGrant(id=g['id'],account_id=account_map[key],
                permission=g['permission'],resource=g['resource'],privilege=g['privilege'],
                cross_department=g['cross_department'],last_verified_use=parse_time(g['last_verified_use']),
                status=g['status']))
        session.flush()
        for r in original['reviews']:
            session.add(Review(id=r['id'],grant_id=r['grant_id'],status=r['status'],
                reviewer=r['reviewer'],decided_at=parse_time(r['decided_at'])))
        for a in original['audit_logs']:
            session.add(AuditLog(id=a['id'],created_at=parse_time(a['created_at']),
                actor=a['actor'],action=a['action'],entity=a['entity'],details=a['details']))
        session.add(AuditLog(id=max([a['id'] for a in original['audit_logs']] or [0])+1, created_at=now_utc(),actor='Migration',
            action='PHASE1_IMPORTED',entity='AccessGuard research lab',
            details=f'Imported {len(original["identities"])} identities and {len(original["access_grants"])} grants from SQLite. Account ownership inferred from Phase 1 mapping, not externally verified.'))
        session.flush()
        if session.bind.dialect.name=='postgresql':
            # SQLite preserved existing integer IDs; advance PostgreSQL sequences.
            for table in ('access_grants','reviews','audit_logs'):
                session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), (SELECT COUNT(*) > 0 FROM {table}))"))
        session.commit()
    print(f'Imported {len(original["identities"])} identities, {len(account_map)} technical accounts, {len(original["access_grants"])} grants, {len(original["reviews"])} reviews.')
    print('Original SQLite source preserved.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sqlite', type=Path,required=True,help='Path to the old Phase 1 backend/accessguard.db')
    args=p.parse_args()
    run(args.sqlite)
