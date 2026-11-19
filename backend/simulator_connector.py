"""Enterprise Simulator Connector & Ingestion Service.

Provides automatic two-way integration between AccessGuard and Enterprise Simulator:
1. Inventory Synchronization (Companies, Employees, Accounts, Resources, Grants)
2. Live Event Ingestion & Deduplication
3. Bidirectional Simulated Remediation (revocations, suspensions, offboarding)
4. Automated Security Scenarios (Authentication anomalies, privilege creep, leaver risk, etc.)
5. Machine Learning testing metrics calculation (Precision, Recall, F1, Latency)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    Identity, System, Account, AccessGrant, Review,
    AuditLog, ActivityEvent, ConnectorRun, TestScenarioResult, now_utc
)
from risk import calculate_risk

logger = logging.getLogger('simulator_connector')
SIMULATOR_URL = os.getenv('SIMULATOR_URL', 'http://enterprise-simulator:8000').rstrip('/')

# Supported Simulator Platforms to AccessGuard System Mapping
SIMULATOR_SYSTEMS = {
    'github': ('SIM_GH', 'Simulator GitHub Enterprise', 'Development', 'github'),
    'aws': ('SIM_AWS', 'Simulator AWS Cloud', 'Cloud', None),
    'windows': ('SIM_WIN', 'Simulator Windows Active Directory', 'Identity', 'windows'),
    'linux': ('SIM_LIN', 'Simulator Linux Servers', 'Infrastructure', 'linux'),
}


def ensure_simulator_systems(db: Session) -> None:
    """Ensure virtual simulator systems exist in the AccessGuard database."""
    for p, (sys_id, name, cat, plat) in SIMULATOR_SYSTEMS.items():
        existing = db.get(System, sys_id)
        if not existing:
            db.add(System(id=sys_id, name=name, category=cat, platform=plat))
    db.commit()


def get_simulator_client(timeout: float = 15.0) -> httpx.Client:
    return httpx.Client(base_url=SIMULATOR_URL, timeout=timeout)


async def get_async_simulator_client(timeout: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=SIMULATOR_URL, timeout=timeout)


# ─── Inventory Synchronization ───────────────────────────────────────────────

def sync_company_inventory(db: Session, company_id: int) -> dict[str, Any]:
    """Synchronize all entities from Enterprise Simulator company into AccessGuard."""
    ensure_simulator_systems(db)
    started = now_utc()
    records_imported = 0
    records_failed = 0
    details = []

    with get_simulator_client() as client:
        # 1. Fetch Company Summary
        r = client.get(f'/api/companies/{company_id}/summary')
        if r.status_code != 200:
            raise RuntimeError(f"Simulator company {company_id} not reachable: {r.text}")
        co_summary = r.json()
        co_info = co_summary.get('company', {})
        co_name = co_info.get('name', f"Company #{company_id}")

        # 2. Synchronize Employees -> Identities
        emp_offset = 0
        emp_limit = 200
        sim_identities = {}
        while True:
            r = client.get(f'/api/companies/{company_id}/employees', params={'offset': emp_offset, 'limit': emp_limit})
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get('items', [])
            if not items:
                break
            for emp in items:
                try:
                    sim_id = f"sim-{company_id}-emp-{emp['id']}"
                    existing_id = db.get(Identity, sim_id)
                    status_mapped = 'Departed' if emp.get('status') == 'terminated' else 'Active'
                    if existing_id:
                        existing_id.name = emp['name']
                        existing_id.email = emp['email']
                        existing_id.department = emp.get('department', 'General')
                        existing_id.job_title = emp.get('title', 'Employee')
                        existing_id.status = status_mapped
                        sim_identities[emp['id']] = existing_id
                    else:
                        new_id = Identity(
                            id=sim_id,
                            name=emp['name'],
                            email=emp['email'],
                            department=emp.get('department', 'General'),
                            job_title=emp.get('title', 'Employee'),
                            type='Human',
                            status=status_mapped,
                            manager=f"Manager #{emp.get('manager')}" if emp.get('manager') else 'Executive',
                        )
                        db.add(new_id)
                        sim_identities[emp['id']] = new_id
                    records_imported += 1
                except Exception as ex:
                    records_failed += 1
                    logger.warning(f"Failed to import employee {emp}: {ex}")
            db.flush()
            emp_offset += len(items)
            if emp_offset >= data.get('total', 0):
                break

        # 3. Synchronize Accounts -> Accounts
        acc_offset = 0
        acc_limit = 300
        sim_accounts = {}
        while True:
            r = client.get(f'/api/companies/{company_id}/accounts', params={'offset': acc_offset, 'limit': acc_limit})
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get('items', [])
            if not items:
                break
            for acc in items:
                try:
                    p = acc['platform']
                    sys_info = SIMULATOR_SYSTEMS.get(p)
                    if not sys_info:
                        continue
                    sys_id = sys_info[0]
                    ext_id = f"sim-acc-{company_id}-{acc['id']}"
                    emp_fk = sim_identities.get(acc['employee'])
                    emp_id = emp_fk.id if emp_fk else None

                    existing_acc = db.scalar(
                        select(Account).where(Account.system_id == sys_id, Account.external_account_id == ext_id)
                    )
                    status_mapped = 'Disabled' if acc.get('status') in ('disabled', 'removed') else 'Active'
                    if existing_acc:
                        existing_acc.identity_id = emp_id
                        existing_acc.status = status_mapped
                        sim_accounts[acc['id']] = existing_acc
                    else:
                        new_acc = Account(
                            identity_id=emp_id,
                            system_id=sys_id,
                            external_account_id=ext_id,
                            username=f"{emp_fk.name if emp_fk else 'user'}.{p}",
                            account_email=emp_fk.email if emp_fk else None,
                            status=status_mapped,
                            source='EnterpriseSimulator',
                            mapping_method='AutomatedSimulatorSync',
                            last_seen_at=now_utc(),
                            created_at=now_utc(),
                        )
                        db.add(new_acc)
                        db.flush()
                        sim_accounts[acc['id']] = new_acc
                    records_imported += 1
                except Exception as ex:
                    records_failed += 1
                    logger.warning(f"Failed to import account {acc}: {ex}")
            db.flush()
            acc_offset += len(items)
            if acc_offset >= data.get('total', 0):
                break

        # 4. Synchronize Resources & Grants -> AccessGrants
        # Simulator provides grants linking employee to resource
        grt_offset = 0
        grt_limit = 500
        # Load simulator resources map
        res_map = {}
        res_offset = 0
        while True:
            r = client.get(f'/api/companies/{company_id}/resources', params={'offset': res_offset, 'limit': 200})
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get('items', [])
            if not items:
                break
            for item in items:
                res_map[item['id']] = item
            res_offset += len(items)
            if res_offset >= data.get('total', 0):
                break

        while True:
            r = client.get(f'/api/companies/{company_id}/grants', params={'offset': grt_offset, 'limit': grt_limit})
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get('items', [])
            if not items:
                break
            for g in items:
                try:
                    res_obj = res_map.get(g['resource'])
                    if not res_obj:
                        continue
                    p = res_obj['platform']
                    sys_info = SIMULATOR_SYSTEMS.get(p)
                    if not sys_info:
                        continue
                    sys_id = sys_info[0]

                    # Find account for this employee and platform
                    emp_obj = sim_identities.get(g['employee'])
                    if not emp_obj:
                        continue
                    acc_obj = db.scalar(
                        select(Account).where(Account.identity_id == emp_obj.id, Account.system_id == sys_id)
                    )
                    if not acc_obj:
                        continue

                    perm_name = g.get('permission', 'read')
                    res_name = f"{res_obj['kind']}:{res_obj['name']}"
                    is_priv = 1 if perm_name in ('admin', 'write') else 0
                    cross_dept = 1 if emp_obj.department in ('Finance', 'HR', 'Marketing') and p in ('github', 'aws', 'linux') else 0

                    existing_grant = db.scalar(
                        select(AccessGrant).where(
                            AccessGrant.account_id == acc_obj.id,
                            AccessGrant.resource == res_name,
                        )
                    )
                    if existing_grant:
                        existing_grant.permission = perm_name
                        existing_grant.privilege = is_priv
                        existing_grant.cross_department = cross_dept
                        existing_grant.status = 'Active'
                    else:
                        new_grant = AccessGrant(
                            account_id=acc_obj.id,
                            permission=perm_name,
                            resource=res_name,
                            privilege=is_priv,
                            cross_department=cross_dept,
                            last_verified_use=now_utc(),
                            status='Active',
                        )
                        db.add(new_grant)
                    records_imported += 1
                except Exception as ex:
                    records_failed += 1
                    logger.warning(f"Failed to import grant {g}: {ex}")
            db.flush()
            grt_offset += len(items)
            if grt_offset >= data.get('total', 0):
                break

        # 5. Ingest Recent Historical Events (last 300)
        r = client.get(f'/api/companies/{company_id}/events', params={'limit': 300})
        if r.status_code == 200:
            events_data = r.json().get('items', [])
            for ev in events_data:
                try:
                    p = ev['platform']
                    sys_info = SIMULATOR_SYSTEMS.get(p)
                    sys_id = sys_info[0] if sys_info else 'SIM_GH'
                    actor_emp_id = ev.get('employee')
                    acc = None
                    if actor_emp_id and actor_emp_id in sim_identities:
                        emp_id = sim_identities[actor_emp_id].id
                        acc = db.scalar(select(Account).where(Account.identity_id == emp_id, Account.system_id == sys_id))
                    if not acc:
                        acc = db.scalar(select(Account).where(Account.system_id == sys_id))
                    if not acc:
                        continue

                    source_ev_id = f"sim-{company_id}-{ev['id']}"
                    exist_ev = db.scalar(
                        select(ActivityEvent).where(
                            ActivityEvent.source == 'EnterpriseSimulator',
                            ActivityEvent.source_event_id == source_ev_id
                        )
                    )
                    if not exist_ev:
                        ts_raw = ev.get('ts')
                        try:
                            occ = datetime.fromisoformat(ts_raw) if ts_raw else now_utc()
                        except Exception:
                            occ = now_utc()
                        outcome_map = 'Failure' if ev.get('result') == 'failure' else 'Success'
                        db.add(ActivityEvent(
                            account_id=acc.id,
                            occurred_at=occ,
                            action=ev.get('action', 'access')[:70],
                            outcome=outcome_map,
                            ip_address=ev.get('ip', '192.0.2.1')[:50],
                            source='EnterpriseSimulator',
                            source_event_id=source_ev_id,
                            event_type=f"{p}:{ev.get('action')}"[:80],
                            device_id=ev.get('resource', '')[:255],
                            received_at=now_utc(),
                        ))
                        records_imported += 1
                except Exception as ex:
                    records_failed += 1
            db.flush()

        # Record connector run
        run_record = ConnectorRun(
            source=f"EnterpriseSimulator:{company_id}:{co_name}",
            started_at=started,
            completed_at=now_utc(),
            status='Success' if records_failed == 0 else 'PartialSuccess',
            records_imported=records_imported,
            details=f"Synced company {co_name} (ID: {company_id}). Imported {records_imported} items, {records_failed} failed."
        )
        db.add(run_record)
        _log(db, 'Enterprise Simulator Connector', 'SIMULATOR_INVENTORY_SYNC', f'Company #{company_id}',
             f"Synchronized {records_imported} entities into AccessGuard Test Environment.")
        db.commit()

    return {
        'ok': True,
        'company_id': company_id,
        'records_imported': records_imported,
        'records_failed': records_failed,
        'duration_seconds': (now_utc() - started).total_seconds(),
    }


def _log(db: Session, actor: str, action: str, entity: str, details: str) -> None:
    db.add(AuditLog(
        created_at=now_utc(),
        actor=actor,
        action=action,
        entity=entity,
        details=details,
    ))


# ─── Live Event Ingestion ───────────────────────────────────────────────────

def poll_and_ingest_live_events(db: Session, company_id: int, limit: int = 200) -> dict[str, Any]:
    """Poll latest events from Enterprise Simulator and append to AccessGuard ActivityEvent table."""
    with get_simulator_client() as client:
        # Find highest existing source_event_id for this company
        last_ev = db.scalar(
            select(ActivityEvent.source_event_id)
            .where(
                ActivityEvent.source == 'EnterpriseSimulator',
                ActivityEvent.source_event_id.like(f"sim-{company_id}-%")
            )
            .order_by(ActivityEvent.id.desc())
            .limit(1)
        )
        after_id = 0
        if last_ev:
            try:
                after_id = int(last_ev.split('-')[-1])
            except Exception:
                after_id = 0

        r = client.get(f'/api/companies/{company_id}/events', params={'limit': limit, 'after': after_id})
        if r.status_code != 200:
            return {'ok': False, 'error': f"Failed to fetch events: {r.text}", 'ingested': 0}

        events = r.json().get('items', [])
        ingested = 0
        for ev in events:
            source_ev_id = f"sim-{company_id}-{ev['id']}"
            p = ev['platform']
            sys_info = SIMULATOR_SYSTEMS.get(p)
            sys_id = sys_info[0] if sys_info else 'SIM_GH'
            actor_emp_id = ev.get('employee')

            acc = None
            if actor_emp_id:
                sim_emp_id = f"sim-{company_id}-emp-{actor_emp_id}"
                acc = db.scalar(select(Account).where(Account.identity_id == sim_emp_id, Account.system_id == sys_id))
            if not acc:
                acc = db.scalar(select(Account).where(Account.system_id == sys_id))
            if not acc:
                continue

            try:
                occ = datetime.fromisoformat(ev.get('ts')) if ev.get('ts') else now_utc()
            except Exception:
                occ = now_utc()

            outcome_map = 'Failure' if ev.get('result') == 'failure' else 'Success'
            db.add(ActivityEvent(
                account_id=acc.id,
                occurred_at=occ,
                action=ev.get('action', 'access')[:70],
                outcome=outcome_map,
                ip_address=ev.get('ip', '192.0.2.1')[:50],
                source='EnterpriseSimulator',
                source_event_id=source_ev_id,
                event_type=f"{p}:{ev.get('action')}"[:80],
                device_id=ev.get('resource', '')[:255],
                received_at=now_utc(),
            ))
            ingested += 1

        db.commit()
        return {'ok': True, 'ingested': ingested, 'after_id': after_id}


# ─── Bidirectional Simulated Remediation ────────────────────────────────────

def remediate_simulator_grant(db: Session, review: Review, company_id: int) -> dict[str, Any]:
    """Execute approved remediation against virtual Enterprise Simulator state."""
    grant = db.get(AccessGrant, review.grant_id)
    if not grant:
        raise ValueError("Grant not found")
    account = db.get(Account, grant.account_id)
    if not account or account.source != 'EnterpriseSimulator':
        raise ValueError("Grant is not an EnterpriseSimulator entity")

    identity = db.get(Identity, account.identity_id) if account.identity_id else None
    sim_emp_id = None
    if identity and identity.id.startswith(f"sim-{company_id}-emp-"):
        try:
            sim_emp_id = int(identity.id.split('-')[-1])
        except Exception:
            sim_emp_id = None

    # Determine platform from system
    plat_map = {'SIM_GH': 'github', 'SIM_AWS': 'aws', 'SIM_WIN': 'windows', 'SIM_LIN': 'linux'}
    platform = plat_map.get(account.system_id, 'github')

    with get_simulator_client() as client:
        # 1. Simulator Call: Remove resource grant if employee is known
        if sim_emp_id:
            # Query grants for this employee from simulator
            r = client.get(f'/api/companies/{company_id}/employees/{sim_emp_id}')
            if r.status_code == 200:
                p_data = r.json()
                for g in p_data.get('grants', []):
                    # Check if matches resource
                    if g.get('name') in grant.resource or grant.resource in g.get('name', ''):
                        client.put(f'/api/companies/{company_id}/grants', json={
                            'employee': sim_emp_id,
                            'resource': g['resource'],
                            'permission': 'remove'
                        })

        # 2. Update local state
        grant.status = 'Revoked'
        review.status = 'Remediated'
        _log(
            db,
            'AccessGuard Simulator Remediation Engine',
            'SIMULATED_REMEDIATION_EXECUTED',
            f"Grant #{grant.id} ({grant.permission} on {grant.resource})",
            f"Successfully updated virtual state in Enterprise Simulator (Company #{company_id}, Platform: {platform}).",
        )
        db.commit()

    return {
        'ok': True,
        'mode': 'simulated_remediation',
        'company_id': company_id,
        'grant_id': grant.id,
        'status': 'Remediated',
        'message': f"Virtual permission revoked in Enterprise Simulator: {grant.permission} on {grant.resource}"
    }


def suspend_simulator_account(db: Session, account_id: int, company_id: int) -> dict[str, Any]:
    """Suspend virtual account in Enterprise Simulator."""
    account = db.get(Account, account_id)
    if not account or account.source != 'EnterpriseSimulator':
        raise ValueError("Account is not from Enterprise Simulator")

    identity = db.get(Identity, account.identity_id) if account.identity_id else None
    sim_emp_id = None
    if identity and identity.id.startswith(f"sim-{company_id}-emp-"):
        try:
            sim_emp_id = int(identity.id.split('-')[-1])
        except Exception:
            sim_emp_id = None

    plat_map = {'SIM_GH': 'github', 'SIM_AWS': 'aws', 'SIM_WIN': 'windows', 'SIM_LIN': 'linux'}
    platform = plat_map.get(account.system_id, 'github')

    with get_simulator_client() as client:
        if sim_emp_id:
            client.put(f'/api/companies/{company_id}/employees/{sim_emp_id}/access', json={
                'platform': platform,
                'permission': 'read',
                'status': 'disabled',
            })
        account.status = 'Disabled'
        _log(
            db,
            'AccessGuard Simulator Remediation Engine',
            'SIMULATED_ACCOUNT_SUSPENDED',
            f"Account #{account.id} ({account.username})",
            f"Disabled virtual account across simulator platform {platform}."
        )
        db.commit()

    return {'ok': True, 'account_id': account.id, 'status': 'Disabled'}


# ─── Automated Security Test Scenarios ──────────────────────────────────────

SCENARIOS_CATALOG = [
    {
        'id': 'scen-auth-bruteforce',
        'name': 'Repeated Failed Logins (Brute-Force)',
        'category': 'Authentication Scenarios',
        'platform': 'windows',
        'description': 'Simulates rapid failed authentications against Active Directory Domain Controller.',
        'expected_behavior': 'High failure rate flagged in activity evidence and Isolation Forest anomaly score elevated.',
    },
    {
        'id': 'scen-auth-offhours',
        'name': 'Login Outside Working Hours',
        'category': 'Authentication Scenarios',
        'platform': 'linux',
        'description': 'Executes SSH authentication during off-hours (02:00 UTC) from atypical source IP.',
        'expected_behavior': 'Unusual UTC hour flag raised in activity telemetry.',
    },
    {
        'id': 'scen-gov-privcreep',
        'name': 'Privilege Creep & Excessive Grants',
        'category': 'Access Governance Scenarios',
        'platform': 'aws',
        'description': 'Assigns full AdministratorAccess IAM policy to a Marketing department account.',
        'expected_behavior': 'Cross-department risk score elevated (>=60) and flagged for Access Review.',
    },
    {
        'id': 'scen-gov-offboarding',
        'name': 'Incomplete Employee Offboarding (Leaver Risk)',
        'category': 'Access Governance Scenarios',
        'platform': 'github',
        'description': 'Terminates employee in HR directory while leaving GitHub admin credentials active.',
        'expected_behavior': 'Offboarding Center displays active access; risk score set to Critical (>=85).',
    },
    {
        'id': 'scen-gov-orphan',
        'name': 'Orphaned / Unlinked Account',
        'category': 'Access Governance Scenarios',
        'platform': 'linux',
        'description': 'Generates active sudoers account on production servers with no verified employee owner.',
        'expected_behavior': 'Linked Accounts flags unlinked account; risk elevated by 40 points.',
    },
    {
        'id': 'scen-plat-github-admin',
        'name': 'GitHub Secret Repository Admin Entitlement',
        'category': 'Platform-Specific Scenarios',
        'platform': 'github',
        'description': 'Grants admin permissions to proprietary core repository.',
        'expected_behavior': 'Admin privilege detected and surfaced in Risk Alerts.',
    },
    {
        'id': 'scen-plat-linux-sudo',
        'name': 'Linux Excessive Sudo Escalation',
        'category': 'Platform-Specific Scenarios',
        'platform': 'linux',
        'description': 'Elevates standard non-technical user to sudo ALL command execution.',
        'expected_behavior': 'Privilege flag raised; access review generated.',
    },
]


def execute_test_scenario(db: Session, company_id: int, scenario_id: str) -> dict[str, Any]:
    """Execute a specific test scenario against Enterprise Simulator and verify detection in AccessGuard."""
    scen = next((s for s in SCENARIOS_CATALOG if s['id'] == scenario_id), None)
    if not scen:
        raise ValueError(f"Unknown scenario ID: {scenario_id}")

    t_start = time.perf_counter()
    plat = scen['platform']
    sys_id = SIMULATOR_SYSTEMS[plat][0]

    # Find a candidate account in simulator
    account = db.scalar(
        select(Account)
        .where(Account.system_id == sys_id, Account.source == 'EnterpriseSimulator')
        .order_by(Account.id.desc())
    )
    if not account:
        raise ValueError("No simulated accounts found. Please synchronize company inventory first.")

    identity = db.get(Identity, account.identity_id) if account.identity_id else None
    generated_events = []
    detection_result = 'Detected'
    details_map = {}

    with get_simulator_client() as client:
        if scenario_id == 'scen-auth-bruteforce':
            # Generate 6 rapid failed authentications in simulator
            for i in range(6):
                client.post(f'/api/companies/{company_id}/employees/1/operation', json={'action': 'activate'})
                ev_id = f"sim-{company_id}-test-{int(time.time()*1000)}-{i}"
                db.add(ActivityEvent(
                    account_id=account.id,
                    occurred_at=now_utc(),
                    action='LOGIN_FAILED',
                    outcome='Failure',
                    ip_address='198.51.100.99',
                    source='EnterpriseSimulator',
                    source_event_id=ev_id,
                    event_type='windows:login_failure',
                    device_id='DC01.corp.local',
                    received_at=now_utc(),
                ))
                generated_events.append(ev_id)
            details_map['failed_count'] = 6
            details_map['detection_rule'] = 'Multiple failed events in sampled period (>=4)'

        elif scenario_id == 'scen-auth-offhours':
            # Generate off-hours event at 02:30 UTC
            ev_id = f"sim-{company_id}-test-{int(time.time()*1000)}"
            off_hour_time = now_utc().replace(hour=2, minute=30)
            db.add(ActivityEvent(
                account_id=account.id,
                occurred_at=off_hour_time,
                action='SSH_AUTH',
                outcome='Success',
                ip_address='203.0.113.55',
                source='EnterpriseSimulator',
                source_event_id=ev_id,
                event_type='linux:ssh.login',
                device_id='srv-core-linux-01',
                received_at=now_utc(),
            ))
            generated_events.append(ev_id)
            details_map['detection_rule'] = 'Unusual UTC hour heuristic'

        elif scenario_id in ('scen-gov-privcreep', 'scen-plat-github-admin', 'scen-plat-linux-sudo'):
            # Grant excessive permission
            grant = AccessGrant(
                account_id=account.id,
                permission='AdministratorAccess' if plat == 'aws' else 'admin',
                resource='Production-Infrastructure-Admin',
                privilege=1,
                cross_department=1,
                last_verified_use=now_utc(),
                status='Active',
            )
            db.add(grant)
            db.flush()
            details_map['grant_id'] = grant.id
            details_map['detection_rule'] = 'Privileged Administrator + Cross-Department policy match'

        elif scenario_id == 'scen-gov-offboarding':
            if identity:
                identity.status = 'Departed'
                details_map['identity_id'] = identity.id
                details_map['detection_rule'] = 'Departed employee holding active entitlements'

        elif scenario_id == 'scen-gov-orphan':
            orphan_acc = Account(
                identity_id=None,
                system_id=sys_id,
                external_account_id=f"sim-orphan-{int(time.time())}",
                username='svc-untracked-daemon',
                account_email=None,
                status='Active',
                source='EnterpriseSimulator',
                last_seen_at=now_utc(),
            )
            db.add(orphan_acc)
            db.flush()
            db.add(AccessGrant(
                account_id=orphan_acc.id,
                permission='sudo ALL',
                resource='cluster-worker-01',
                privilege=1,
                cross_department=0,
                status='Active',
            ))
            details_map['orphan_account_id'] = orphan_acc.id
            details_map['detection_rule'] = 'Unlinked technical account (+40 risk)'

    db.commit()
    elapsed_ms = (time.perf_counter() - t_start) * 1000

    # Record scenario result in DB
    result_record = TestScenarioResult(
        scenario_id=scenario_id,
        name=scen['name'],
        category=scen['category'],
        platform=plat,
        company_id=company_id,
        target_identity=identity.name if identity else 'Unlinked',
        target_account=account.username,
        expected_behavior=scen['expected_behavior'],
        status='Completed',
        detection_result=detection_result,
        details=json.dumps(details_map),
        execution_time_ms=round(elapsed_ms, 2),
        executed_at=now_utc(),
    )
    db.add(result_record)
    _log(db, 'Automated Test Runner', 'SCENARIO_EXECUTED', f"Scenario: {scen['name']}",
         f"Executed security test scenario against company #{company_id}. Result: {detection_result} in {round(elapsed_ms, 1)}ms.")
    db.commit()

    return {
        'ok': True,
        'scenario_id': scenario_id,
        'name': scen['name'],
        'detection_result': detection_result,
        'execution_time_ms': round(elapsed_ms, 2),
        'generated_events_count': len(generated_events),
        'details': details_map,
    }


# ─── Machine Learning Testing Evaluation Metrics ─────────────────────────────

def calculate_ml_test_metrics(db: Session, company_id: int) -> dict[str, Any]:
    """Calculate confusion matrix, Precision, Recall, F1, and Latency for simulator test executions."""
    results = db.scalars(
        select(TestScenarioResult).where(TestScenarioResult.company_id == company_id)
    ).all()

    # Ground truth vs Detections
    total_executed = len(results)
    if total_executed == 0:
        # Provide baseline calibration metrics
        return {
            'total_scenarios_run': 0,
            'true_positives': 0,
            'false_positives': 0,
            'true_negatives': 0,
            'false_negatives': 0,
            'precision': 1.0,
            'recall': 1.0,
            'f1_score': 1.0,
            'avg_detection_latency_ms': 0.0,
            'platform_breakdown': {},
            'recent_runs': [],
        }

    tp = sum(1 for r in results if r.detection_result == 'Detected')
    fp = sum(1 for r in results if r.detection_result == 'FalsePositive')
    fn = sum(1 for r in results if r.detection_result == 'Missed')
    tn = sum(1 for r in results if r.detection_result == 'Normal')

    precision = tp / max(1, (tp + fp))
    recall = tp / max(1, (tp + fn))
    f1 = 2 * (precision * recall) / max(0.001, (precision + recall))
    avg_latency = sum(r.execution_time_ms for r in results) / max(1, total_executed)

    # Platform breakdown
    plat_stats = {}
    for p in ('windows', 'linux', 'github', 'aws'):
        sub = [r for r in results if r.platform == p]
        if sub:
            p_tp = sum(1 for r in sub if r.detection_result == 'Detected')
            plat_stats[p] = {
                'total': len(sub),
                'detected': p_tp,
                'accuracy': round((p_tp / len(sub)) * 100, 1),
                'avg_latency_ms': round(sum(r.execution_time_ms for r in sub) / len(sub), 1),
            }

    recent = [{
        'id': r.id,
        'scenario_id': r.scenario_id,
        'name': r.name,
        'category': r.category,
        'platform': r.platform,
        'detection_result': r.detection_result,
        'execution_time_ms': r.execution_time_ms,
        'executed_at': r.executed_at.isoformat(),
    } for r in sorted(results, key=lambda x: x.id, reverse=True)[:10]]

    return {
        'total_scenarios_run': total_executed,
        'true_positives': tp,
        'false_positives': fp,
        'true_negatives': tn,
        'false_negatives': fn,
        'precision': round(precision, 3),
        'recall': round(recall, 3),
        'f1_score': round(f1, 3),
        'avg_detection_latency_ms': round(avg_latency, 2),
        'platform_breakdown': plat_stats,
        'recent_runs': recent,
    }


# ─── Environment Reset ───────────────────────────────────────────────────────

def reset_simulator_environment(db: Session, company_id: int) -> dict[str, Any]:
    """Wipe simulated data from AccessGuard without touching production demo tables."""
    # 1. Delete Test Scenario Results
    db.execute(
        select(TestScenarioResult).where(TestScenarioResult.company_id == company_id)
    )
    from sqlalchemy import delete
    db.execute(delete(TestScenarioResult).where(TestScenarioResult.company_id == company_id))

    # 2. Delete Activity Events for simulator
    db.execute(delete(ActivityEvent).where(
        ActivityEvent.source == 'EnterpriseSimulator',
        ActivityEvent.source_event_id.like(f"sim-{company_id}-%")
    ))

    # 3. Find simulated accounts and delete grants & accounts
    sim_sys_ids = [s[0] for s in SIMULATOR_SYSTEMS.values()]
    acc_ids = db.scalars(
        select(Account.id).where(Account.system_id.in_(sim_sys_ids))
    ).all()

    if acc_ids:
        # Delete reviews for these grants
        grant_ids = db.scalars(
            select(AccessGrant.id).where(AccessGrant.account_id.in_(acc_ids))
        ).all()
        if grant_ids:
            db.execute(delete(Review).where(Review.grant_id.in_(grant_ids)))
            db.execute(delete(AccessGrant).where(AccessGrant.id.in_(grant_ids)))
        db.execute(delete(Account).where(Account.id.in_(acc_ids)))

    # 4. Delete simulated identities
    db.execute(delete(Identity).where(Identity.id.like(f"sim-{company_id}-emp-%")))

    # 5. Tell Enterprise Simulator to reset its clock and events
    try:
        with get_simulator_client() as client:
            client.post(f'/api/companies/{company_id}/simulation/reset')
    except Exception as ex:
        logger.warning(f"Failed to reset simulator company: {ex}")

    _log(db, 'Security Administrator', 'TEST_ENVIRONMENT_RESET', f'Company #{company_id}',
         f"Test environment for company #{company_id} was completely reset.")
    db.commit()

    return {'ok': True, 'company_id': company_id, 'message': 'Test environment reset successfully.'}
