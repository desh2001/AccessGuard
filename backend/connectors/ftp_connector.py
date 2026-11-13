"""Dialog Access Log FTP Connector.

Connects to the Dialog log server via FTP (or local spool directory fallback),
downloads access logs & entitlement dumps exported by `dialog-access-log`,
and ingests them into the centralized PostgreSQL AccessGuard database.
"""
from __future__ import annotations
import csv
import io
import os
from datetime import datetime, timezone
from ftplib import FTP, error_perm
from pathlib import Path
from typing import Any
from sqlalchemy import select
from models import Account, AccessGrant, ActivityEvent, System, ConnectorRun, AuditLog, now_utc

REQUIRED_ENTITLEMENT_COLS = {'external_account_id', 'username', 'permission', 'resource', 'system_id'}
REQUIRED_ACTIVITY_COLS = {'external_account_id', 'system_id', 'action', 'outcome'}


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return now_utc()
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return now_utc()


def process_csv_content(db, content: str, filename: str) -> tuple[int, int]:
    """Parse CSV text and insert grants and/or activity events.

    Returns (grants_count, activity_count).
    """
    reader = csv.DictReader(io.StringIO(content))
    fieldnames = set(reader.fieldnames or [])

    grants_count = 0
    activity_count = 0

    is_entitlements = REQUIRED_ENTITLEMENT_COLS.issubset(fieldnames)
    is_activity = REQUIRED_ACTIVITY_COLS.issubset(fieldnames)

    if not is_entitlements and not is_activity:
        # Check partial entitlement match
        if {'external_account_id', 'username', 'permission', 'resource'}.issubset(fieldnames):
            is_entitlements = True

    for row in reader:
        sys_id = (row.get('system_id') or 'GH').strip()
        if not db.get(System, sys_id):
            # Fallback to GH or create default if not found
            sys_id = 'GH'

        ext_id = (row.get('external_account_id') or '').strip()
        if not ext_id:
            continue

        username = (row.get('username') or ext_id).strip()
        email = (row.get('account_email') or '').strip() or None

        # Look up or register unlinked account
        account = db.scalar(
            select(Account).where(
                Account.system_id == sys_id,
                Account.external_account_id == ext_id,
            )
        )
        if account is None:
            account = Account(
                identity_id=None,
                system_id=sys_id,
                external_account_id=ext_id,
                username=username,
                account_email=email,
                status='Active',
                source='FTP:dialog-access-log',
                mapping_method=None,
                last_seen_at=now_utc(),
                created_at=now_utc(),
            )
            db.add(account)
            db.flush()

        # 1. Process Entitlement Grant
        if is_entitlements and row.get('permission') and row.get('resource'):
            perm = row['permission'].strip()
            res = row['resource'].strip()
            existing_grant = db.scalar(
                select(AccessGrant).where(
                    AccessGrant.account_id == account.id,
                    AccessGrant.permission == perm,
                    AccessGrant.resource == res,
                )
            )
            if existing_grant is None:
                priv = int(perm.lower() in ('admin', 'sudo', 'owner', 'root'))
                db.add(AccessGrant(
                    account_id=account.id,
                    permission=perm,
                    resource=res,
                    privilege=priv,
                    cross_department=0,
                    last_verified_use=now_utc(),
                    status='Active',
                ))
                grants_count += 1

        # 2. Process Activity Log Event
        if is_activity and row.get('action') and row.get('outcome'):
            action = row['action'].strip()
            outcome = 'Success' if row['outcome'].strip().lower() == 'success' else 'Failure'
            ip = (row.get('ip_address') or '').strip() or None
            occurred_at = _parse_timestamp(row.get('occurred_at'))

            db.add(ActivityEvent(
                account_id=account.id,
                occurred_at=occurred_at,
                action=action,
                outcome=outcome,
                ip_address=ip,
                source='FTP:dialog-access-log',
            ))
            activity_count += 1
            account.last_seen_at = occurred_at

    return grants_count, activity_count


def sync_dialog_ftp(
    db,
    host: str = '127.0.0.1',
    port: int = 21,
    user: str = 'dialog_access',
    password: str = '',
    remote_dir: str = '/incoming_logs',
    local_spool_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Connect to FTP server or local spool directory to ingest Dialog access logs."""
    started_at = now_utc()
    files_processed: list[str] = []
    total_grants = 0
    total_activity = 0
    connection_mode = 'ftp'
    error_message: str | None = None

    if local_spool_dir is None:
        local_spool_dir = Path(__file__).resolve().parent.parent / 'sample_imports' / 'ftp_spool'
    else:
        local_spool_dir = Path(local_spool_dir)

    # ── Attempt 1: Connect via live FTP server ─────────────────────────────
    ftp_connected = False
    ftp = None
    try:
        ftp = FTP()
        ftp.connect(host=host, port=port, timeout=3)
        if user:
            ftp.login(user=user, passwd=password)
        else:
            ftp.login()
        ftp_connected = True
        try:
            ftp.cwd(remote_dir)
        except error_perm:
            pass  # Root / current directory
        
        file_list = []
        try:
            file_list = [f for f in ftp.nlst() if f.endswith(('.csv', '.json', '.log'))]
        except Exception:
            file_list = []

        for filename in file_list:
            buffer = io.BytesIO()
            ftp.retrbinary(f'RETR {filename}', buffer.write)
            content = buffer.getvalue().decode('utf-8', errors='replace')
            g, a = process_csv_content(db, content, filename)
            total_grants += g
            total_activity += a
            files_processed.append(filename)

    except Exception as e:
        error_message = str(e)
        connection_mode = 'local_spool_fallback'
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass

    # ── Attempt 2: If live FTP was offline, use local spool directory ──────
    if not ftp_connected or not files_processed:
        if local_spool_dir.exists():
            for p in sorted(local_spool_dir.glob('*.csv')):
                content = p.read_text(encoding='utf-8-sig', errors='replace')
                g, a = process_csv_content(db, content, p.name)
                total_grants += g
                total_activity += a
                files_processed.append(f'{p.name} (local spool drop)')

    # ── Record Connector Run Provenance & Audit Trail ───────────────────────
    status = 'Success' if files_processed else ('Warning' if error_message else 'Idle')
    details = (
        f"Ingested {len(files_processed)} files via {connection_mode}. "
        f"Created {total_grants} new grants and {total_activity} activity events from Dialog logs."
    )
    if error_message and connection_mode == 'local_spool_fallback':
        details += f" (Note: FTP server '{host}:{port}' was unreachable ({error_message}); processed local spool directory)."

    db.add(ConnectorRun(
        source='FTP:dialog-access-log',
        started_at=started_at,
        completed_at=now_utc(),
        status=status,
        records_imported=total_grants + total_activity,
        details=details,
    ))
    db.add(AuditLog(
        created_at=now_utc(),
        actor='FTP Connector Service',
        action='DIALOG_FTP_SYNC',
        entity='dialog-access-log',
        details=details,
    ))
    db.commit()

    return {
        'status': status,
        'mode': connection_mode,
        'files_processed': files_processed,
        'grants_imported': total_grants,
        'activity_imported': total_activity,
        'total_imported': total_grants + total_activity,
        'details': details,
        'timestamp': now_utc().isoformat(),
    }

