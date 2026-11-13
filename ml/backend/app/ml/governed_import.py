"""Demo-only, offline ingestion of approved managed resource policies and events.

Collectors must ONLY export company-managed applications/assets; never raw
personal browsing history, search terms, website paths, or command-line args.
Command-line source attestations are NOT enterprise-grade signatures.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import (Account, GovernedResourcePolicy, GovernedResourceUse)
from .governed_resources import SUPPORTED_KINDS


def parse_dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)


def validate_key(key):
    key=(key or '').strip()
    if not key or len(key)>180 or any(c in key for c in '/?#@\\') or '://' in key:
        raise ValueError('Use stable managed asset keys, never full URLs, paths or accounts')
    return key


def import_managed_csv(db:Session, path, *, kind, organization_key='demo',
                       trusted_sources=(), policy_approvers=()):
    """Company-scoped ingestion with explicit approver and collector lists.

    Intentionally rejects unknown resource keys instead of monitoring arbitrary
    web activity. Never use user-supplied verified flags as source trust.
    """
    path=Path(path)
    if path.stat().st_size>10*1024*1024:
        raise ValueError('Prototype importer limited to 10 MiB; use batch ETL in production')
    if kind not in {'policy','usage'}:
        raise ValueError('kind must be policy or usage')
    trusted=set(trusted_sources)
    approvers=set(policy_approvers)
    counts={'created':0,'ignored_duplicate':0,'ignored_not_managed':0}
    with path.open(newline='', encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        for row in reader:
            platform=(row.get('platform') or '').strip()
            rk=(row.get('resource_kind') or '').strip()
            asset=validate_key(row.get('resource_key'))
            if not platform or rk not in SUPPORTED_KINDS:
                raise ValueError('Require platform and supported managed resource kind')
            if kind=='policy':
                author=(row.get('approved_by') or '').strip()
                version=(row.get('policy_version') or '').strip()
                if not author or author not in approvers or not version:
                    raise ValueError('Company-approved policy signer and version required')
                depts=[v.strip() for v in (row.get('allowed_departments') or '').split('|') if v.strip()]
                roles=[v.strip() for v in (row.get('allowed_job_titles') or '').split('|') if v.strip()]
                if not (depts or roles):
                    raise ValueError('Empty access scope gives no governance signal; require explicit mapping')
                key={'organization_key':organization_key,'platform':platform,'resource_kind':rk,
                     'resource_key':asset,'policy_version':version}
                if db.query(GovernedResourcePolicy).filter_by(**key).first():
                    counts['ignored_duplicate']+=1
                    continue
                db.add(GovernedResourcePolicy(**key,allowed_departments=depts,
                       allowed_job_titles=roles,approved_by=author,
                       effective_at=parse_dt(row['effective_at']),active=True))
                counts['created']+=1
            else:
                source=(row.get('source') or '').strip()
                if not source or source not in trusted:
                    raise ValueError('Usage requires a separately approved trusted source')
                if (row.get('outcome') or '').strip()!='observed':
                    counts['ignored_not_managed']+=1
                    continue
                policy=db.query(GovernedResourcePolicy).filter_by(
                    organization_key=organization_key,platform=platform,resource_kind=rk,
                    resource_key=asset,active=True).first()
                if not policy:
                    counts['ignored_not_managed']+=1
                    continue  # never collect generic web browsing without explicit policy
                key=(row.get('event_key') or '').strip()
                if not key:
                    raise ValueError('Event key required for idempotency')
                if db.query(GovernedResourceUse).filter_by(event_key=key).first():
                    counts['ignored_duplicate']+=1
                    continue
                username=(row.get('username') or '').strip()
                account=db.query(Account).filter_by(platform=platform,username=username).first()
                if not account:
                    raise ValueError('Unmapped account must be resolved by identity team')
                db.add(GovernedResourceUse(event_key=key,account_id=account.id,
                       resource_kind=rk,resource_key=asset,
                       occurred_at=parse_dt(row['occurred_at']),source=source,
                       source_verified=True,outcome='observed'))
                counts['created']+=1
    db.commit()
    return counts


def main():
    parser=argparse.ArgumentParser(description='V7 explicitly governed resource import (offline prototype)')
    parser.add_argument('--kind',choices=['policy','usage'],required=True)
    parser.add_argument('--csv',required=True)
    parser.add_argument('--organization-key',default='demo')
    parser.add_argument('--trusted-source',action='append',default=[])
    parser.add_argument('--approved-by',action='append',default=[])
    args=parser.parse_args()
    with SessionLocal() as db:
        stats=import_managed_csv(db,args.csv,kind=args.kind,organization_key=args.organization_key,
                                 trusted_sources=args.trusted_source,policy_approvers=args.approved_by)
    print(stats)

if __name__=='__main__':
    main()
