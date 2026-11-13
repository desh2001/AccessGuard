"""OPTIONAL operator-run read-only GitHub organization snapshot.

No token reaches the dashboard. No writes to GitHub. Run only against your
own authorized testing organization and ensure API access is allowed.

Example:
  GITHUB_READ_TOKEN=... GITHUB_ORG=... python -m connectors.github_readonly
"""
import argparse
from os import getenv
import re
import httpx
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy import select
from database import SessionLocal
from models import System, Account, AccessGrant, ConnectorRun, AuditLog, now_utc

load_dotenv(Path(__file__).resolve().parents[1]/'.env')


def fetch(client, route, **params):
    response=client.get('https://api.github.com'+route,params=params)
    response.raise_for_status()
    payload=response.json()
    if not isinstance(payload,list):
        raise ValueError('Expected list response from GitHub API')
    return payload


def sync(db, org, token, max_repos=10, max_collaborators=100, client=None):
    if not re.fullmatch(r'[A-Za-z0-9-]{1,39}',org):
        raise ValueError('Invalid GitHub organization name')
    if not token:
        raise ValueError('GITHUB_READ_TOKEN missing')
    if not db.get(System,'GH'):
        raise ValueError('No GH system exists: run seed_demo first')
    started=now_utc()
    own_client=client is None
    if own_client:
        client=httpx.Client(timeout=25,headers={
             'Accept':'application/vnd.github+json',
             'Authorization':f'Bearer {token}',
             'X-GitHub-Api-Version':'2026-03-10',
             'User-Agent':'AccessGuard-Research-ReadOnly'})
    count=0
    try:
        repos=fetch(client,f'/orgs/{org}/repos',per_page=min(max_repos,100),type='all')[:max_repos]
        for repo in repos:
            repo_name=repo.get('name','')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',repo_name):
                continue
            collaborators=fetch(client,f'/repos/{org}/{repo_name}/collaborators',
                per_page=min(max_collaborators,100),affiliation='all')[:max_collaborators]
            for person in collaborators:
                user_id=person.get('id')
                if not isinstance(user_id,int):continue
                ext_id=f'github-user:{user_id}'
                account=db.scalar(select(Account).where(Account.system_id=='GH',Account.external_account_id==ext_id))
                if account is None:
                    account=Account(system_id='GH',identity_id=None,external_account_id=ext_id,
                        username=person.get('login','unknown')[:255],account_email=None,
                        status='Active',source='GitHubREST',mapping_method=None,created_at=now_utc())
                    db.add(account);db.flush()
                role=(person.get('role_name') or 'read')[:80]
                resource=f'github.com/{org}/{repo_name}'
                grant=db.scalar(select(AccessGrant).where(AccessGrant.account_id==account.id,
                              AccessGrant.resource==resource,AccessGrant.permission==role))
                if grant is None:
                    db.add(AccessGrant(account_id=account.id,permission=role,resource=resource,
                        privilege=int(role.casefold() in ('admin','maintain','owner')),
                        cross_department=0,last_verified_use=None,status='Active'))
                    count+=1
                elif grant.status=='Revoked':
                    # Previously *simulated* revocation does not imply GitHub was changed.
                    # Keep local decision and record conflicting external observation.
                    db.add(AuditLog(actor='GitHub Sync CLI',action='EXTERNAL_GRANT_STILL_PRESENT',
                        entity=f'Grant #{grant.id}',details='Remote read-only snapshot shows permission; local simulation did not change remote access.',created_at=now_utc()))
        db.add(ConnectorRun(source=f'GitHub:{org}',started_at=started,
            completed_at=now_utc(),status='Success',records_imported=count,
            details=f'Checked up to {max_repos} repositories x {max_collaborators} collaborators; snapshot may be incomplete.'))
        db.add(AuditLog(actor='GitHub Sync CLI',action='READONLY_GITHUB_IMPORT',entity=org,
            details=f'Added {count} new grants; no identity auto-link or external permission changes.',created_at=now_utc()))
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        if own_client:client.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--org',default=getenv('GITHUB_ORG'))
    p.add_argument('--max-repos',type=int,default=10)
    args=p.parse_args()
    if not args.org: p.error('Supply --org or GITHUB_ORG in backend/.env')
    if not 1<=args.max_repos<=100:p.error('max-repos must be 1..100')
    with SessionLocal() as db:
        count=sync(db,args.org,getenv('GITHUB_READ_TOKEN'),max_repos=args.max_repos)
        print(f'Imported {count} new read-only GitHub grants; no remote changes')


if __name__=='__main__':main()
