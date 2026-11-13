"""Read-only exported-entitlement ingest from operator-approved test files.

Run: python -m connectors.csv_import --file sample_imports/linux_accounts.csv --system LIN
No remote commands are executed. Does not infer employee identity from names.
"""
import argparse
import csv
from pathlib import Path
from sqlalchemy import select
from models import Account, AccessGrant, System, ConnectorRun, AuditLog, now_utc
from database import SessionLocal

REQUIRED = {'external_account_id','username','permission','resource'}


def import_csv(db, path: Path, system_id: str):
    if not db.get(System, system_id):
        raise ValueError(f'Unknown system ID: {system_id}; run seed_demo first')
    count = 0
    started=now_utc()
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader=csv.DictReader(f)
        if not REQUIRED.issubset(set(reader.fieldnames or [])):
            raise ValueError(f'CSV must contain {", ".join(sorted(REQUIRED))}')
        for i,row in enumerate(reader, start=2):
            if i>1002: raise ValueError('Maximum 1,000 rows per import to protect the demo database')
            external=(row['external_account_id'] or '').strip()
            username=(row['username'] or '').strip()
            permission=(row['permission'] or '').strip()
            resource=(row['resource'] or '').strip()
            if not all((external,username,permission,resource)) or any(len(v)>255 for v in (external,username,permission,resource)) or len(permission)>80:
                raise ValueError(f'Invalid or overlong field on row {i}')
            account=db.scalar(select(Account).where(Account.system_id==system_id,
                         Account.external_account_id==external))
            if account is None:
                account=Account(identity_id=None,system_id=system_id,
                    external_account_id=external,username=username,
                    account_email=(row.get('account_email') or '').strip() or None,
                    status='Active',source='CSVImport',mapping_method=None,created_at=now_utc())
                db.add(account);db.flush()
            # Don't overwrite manual verified links or simulated grant decisions.
            exists=db.scalar(select(AccessGrant).where(AccessGrant.account_id==account.id,
                             AccessGrant.permission==permission,AccessGrant.resource==resource))
            if exists is None:
                db.add(AccessGrant(account_id=account.id,permission=permission,
                    resource=resource,privilege=int(permission.lower() in ('admin','owner','root')),
                    cross_department=0,last_verified_use=None,status='Active'))
                count+=1
    db.add(ConnectorRun(source=f'CSV:{system_id}',started_at=started,completed_at=now_utc(),
        status='Success',records_imported=count,
        details=f'Imported a local operator-supplied file ({path.name}), source completeness unknown.'))
    db.add(AuditLog(actor='CSV Import CLI',action='READONLY_SNAPSHOT_IMPORT',
        entity=system_id,details=f'Created {count} grant records; owner links untouched; no external writes.',
        created_at=now_utc()))
    db.commit()
    return count


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--file', type=Path,required=True)
    p.add_argument('--system',required=True,help='Existing system ID e.g. LIN or WIN')
    args=p.parse_args()
    with SessionLocal() as db:
        try:
            print(f'Imported {import_csv(db,args.file,args.system)} new grants (local-only)')
        except Exception:
            db.rollback()
            raise


if __name__=='__main__':main()
