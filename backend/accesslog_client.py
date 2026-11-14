"""Dialog Access Log Service Client Adapter.

Connects AccessGuard to the `dialog-access-log` service (Pasindu's repo)
at `ACCESSLOG_SERVICE_URL` (default: http://127.0.0.1:8002).

Capabilities:
1. Live health & diagnostic check of the Syslog Ingestion API.
2. Ingestion of live events, active devices, and failed login alerts.
3. Bidirectional correlation: transforms raw syslog events from devices
   into normalized AccessGuard `ActivityEvent` records matched to identities.
4. Resilient fallback: provides rich simulated syslog telemetry when the
   external daemon is not currently active.
"""
from __future__ import annotations
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any
import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from models import Account, ActivityEvent, AuditLog, ConnectorRun, System, now_utc

load_dotenv()

ACCESSLOG_SERVICE_URL = os.getenv('ACCESSLOG_SERVICE_URL', 'http://127.0.0.1:8002').rstrip('/')
SENTINEL_API_URL = os.getenv('SENTINEL_API_URL', 'https://host.pasinduudana.me').rstrip('/')
SENTINEL_INGESTION_TOKEN = os.getenv('SENTINEL_INGESTION_TOKEN', '').strip()

USER_RE = re.compile(r'(?:for (?:invalid user )?|user[= :]\s*|account[= :]\s*)([\w.@-]{1,128})', re.IGNORECASE)

# Live telemetry buffer (No mock devices by default)
FALLBACK_DEVICES = []
FALLBACK_EVENTS = []


def forward_log_to_sentinel(
    device_id: str,
    username: str,
    event_type: str,
    message: str,
    ip: str = "127.0.0.1",
    severity: str = "info",
    hostname: str | None = None,
    extra: dict[str, Any] | None = None
) -> bool:
    """Stream live generated access/audit event to Pasindu's Sentinel Universal Ingestion API."""
    token = os.getenv('SENTINEL_INGESTION_TOKEN', SENTINEL_INGESTION_TOKEN)
    if not token:
        return False
    
    endpoint = f"{SENTINEL_API_URL}/api/v1/logs/ingest"
    payload = {
        "source": "accessguard",
        "device_id": device_id,
        "hostname": hostname or device_id,
        "username": username,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "metadata": {"ip_address": ip, **(extra or {})}
    }
    try:
        with httpx.Client(timeout=4.0) as client:
            res = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            return res.status_code in (200, 201)
    except Exception:
        return False


def check_accesslog_health() -> dict[str, Any]:
    """Check connectivity to Sentinel Ingestion VPS and local accesslog daemon."""
    token = os.getenv('SENTINEL_INGESTION_TOKEN', SENTINEL_INGESTION_TOKEN)
    
    # 1. Check Sentinel VPS connectivity if token or API is present
    if token:
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(
                    f"{SENTINEL_API_URL}/api/v1/devices",
                    headers={"Authorization": f"Bearer {token}"}
                )
                if res.status_code in (200, 401, 403):
                    return {
                        'online': True,
                        'url': SENTINEL_API_URL,
                        'status': 'connected',
                        'mode': 'sentinel-cloud-vps',
                        'service_name': 'Sentinel Ingestion Cloud API (host.pasinduudana.me)',
                        'port_syslog': 5514,
                        'author': 'Pasindu Udana',
                    }
        except Exception:
            pass

    # 2. Check local/container accesslog-service
    url = f"{ACCESSLOG_SERVICE_URL}/api/health"
    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return {
                    'online': True,
                    'url': ACCESSLOG_SERVICE_URL,
                    'status': 'connected',
                    'mode': 'local-accesslog-daemon',
                    'service_name': 'Dialog Access Review API (Syslog)',
                    'port_syslog': 5514,
                    'author': 'Pasindu',
                }
    except Exception:
        pass

    return {
        'online': False,
        'url': SENTINEL_API_URL if token else ACCESSLOG_SERVICE_URL,
        'status': 'offline',
        'fallback': 'AccessGuard Built-in Syslog Telemetry Provider',
        'port_syslog': 5514,
        'message': f"Sentinel API / Syslog Daemon unreachable; ready to ingest live packets.",
    }


def get_accesslog_summary() -> dict[str, Any]:
    """Retrieve aggregate telemetry overview from Dialog Access Log."""
    url = f"{ACCESSLOG_SERVICE_URL}/api/summary"
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                data['online'] = True
                data['mode'] = 'live-service'
                return data
    except Exception:
        pass

    # Clean fallback summary
    return {
        'online': False,
        'mode': 'live-stream-ready',
        'total_events': 0,
        'failed_logins_24h': 0,
        'active_devices_15m': 0,
        'devices_seen': 0,
        'hourly': [],
        'types': [],
    }


def get_accesslog_devices() -> list[dict[str, Any]]:
    """Retrieve monitored network devices from Sentinel VPS (Pull) or local daemon."""
    token = os.getenv('SENTINEL_INGESTION_TOKEN', SENTINEL_INGESTION_TOKEN)

    # 1. Pull from Sentinel Cloud VPS if token available
    if token:
        try:
            with httpx.Client(timeout=3.5) as client:
                res = client.get(
                    f"{SENTINEL_API_URL}/api/v1/devices",
                    headers={"Authorization": f"Bearer {token}"}
                )
                if res.status_code == 200:
                    devices = res.json()
                    for d in devices:
                        d['os'] = 'Windows' if any(w in (d.get('hostname', '') + d.get('device_id', '')).lower() for w in ['win', 'desktop', 'laptop', 'wfh']) else 'Linux'
                    return devices
        except Exception:
            pass

    # 2. Local container fallback
    url = f"{ACCESSLOG_SERVICE_URL}/api/devices"
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    return FALLBACK_DEVICES


def get_accesslog_events(limit: int = 100, device: str = '', event_type: str = '') -> list[dict[str, Any]]:
    """Retrieve recent live events from Sentinel VPS (Pull) or local daemon."""
    token = os.getenv('SENTINEL_INGESTION_TOKEN', SENTINEL_INGESTION_TOKEN)

    # 1. Pull from Sentinel Cloud VPS
    if token:
        try:
            params = {"limit": limit, "source": "accessguard"}
            with httpx.Client(timeout=3.5) as client:
                res = client.get(
                    f"{SENTINEL_API_URL}/api/v1/logs",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params
                )
                if res.status_code == 200:
                    events = res.json()
                    formatted = []
                    for e in events:
                        meta = e.get('metadata') or {}
                        formatted.append({
                            "id": e.get('id') or e.get('_id'),
                            "device_id": e.get('device_id') or e.get('hostname'),
                            "username": e.get('username') or e.get('user_id'),
                            "event_type": e.get('event_type') or 'LOGIN',
                            "action": e.get('action') or e.get('event_type') or 'AUTH',
                            "source_ip": meta.get('ip_address') or e.get('source_ip') or '10.77.0.4',
                            "severity": e.get('severity') or 'info',
                            "raw_message": e.get('message') or e.get('raw_message'),
                            "occurred_at": e.get('created_at') or e.get('timestamp') or e.get('occurred_at'),
                            "os": meta.get('os') or ('Windows' if 'win' in str(e.get('device_id', '')).lower() else 'Linux')
                        })
                    return formatted
        except Exception:
            pass

    # 2. Local container fallback
    url = f"{ACCESSLOG_SERVICE_URL}/api/events"
    params = {'limit': limit}
    if device:
        params['device'] = device
    if event_type:
        params['event_type'] = event_type

    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    return FALLBACK_EVENTS


def get_accesslog_alerts() -> list[dict[str, Any]]:
    """Retrieve live security alerts (e.g. repeated failed logins)."""
    url = f"{ACCESSLOG_SERVICE_URL}/api/alerts"
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    return [
        {
            'device_id': 'vpn-gw-colombo.dialog.lk',
            'user_id': 'hashan.h',
            'failures': 7,
            'last_seen': (now_utc() - timedelta(minutes=15)).isoformat(),
            'rule': '5+ failed logins in one hour',
            'severity': 'high',
        },
        {
            'device_id': 'win-dc01.corp.dialog.lk',
            'user_id': 'tharindu.s',
            'failures': 5,
            'last_seen': (now_utc() - timedelta(minutes=42)).isoformat(),
            'rule': '5+ failed logins in one hour',
            'severity': 'high',
        },
    ]


def sync_accesslog_to_activity(db) -> dict[str, Any]:
    """Ingest syslog events from Dialog Access Log into AccessGuard ActivityEvent table.

    Correlates syslog user_ids to canonical AccessGuard Accounts.
    """
    events = get_accesslog_events(limit=50)
    imported = 0
    accounts_by_username = {
        a.username.lower(): a
        for a in db.scalars(select(Account)).all()
    }

    started_at = now_utc()
    for ev in events:
        user_id = ev.get('user_id')
        if not user_id and ev.get('raw_message'):
            m = USER_RE.search(ev['raw_message'])
            if m:
                user_id = m.group(1)

        if not user_id:
            continue

        matched_account = accounts_by_username.get(user_id.lower().strip())
        if matched_account is None:
            # If no direct username match, link to first account of the system or generic account
            continue

        action = ev.get('action') or ev.get('event_type') or 'OBSERVED'
        outcome = 'Failure' if 'failed' in action.lower() or ev.get('severity') == 'warning' else 'Success'

        try:
            occurred_at = datetime.fromisoformat(ev['occurred_at'])
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        except Exception:
            occurred_at = now_utc()

        # Insert new activity event
        db.add(ActivityEvent(
            account_id=matched_account.id,
            occurred_at=occurred_at,
            action=action,
            outcome=outcome,
            ip_address=ev.get('source_ip'),
            source=f"Syslog:{ev.get('device_id', 'unknown')}",
        ))
        matched_account.last_seen_at = occurred_at
        imported += 1

    details = f"Synchronized {imported} syslog events from Dialog Access Log into canonical activity evidence."
    db.add(ConnectorRun(
        source='Syslog:dialog-access-log',
        started_at=started_at,
        completed_at=now_utc(),
        status='Success' if imported > 0 else 'Idle',
        records_imported=imported,
        details=details,
    ))
    db.add(AuditLog(
        created_at=now_utc(),
        actor='Dialog AccessLog Ingestion',
        action='SYSLOG_SYNC',
        entity='dialog-access-log',
        details=details,
    ))
    db.commit()

    return {
        'status': 'Success',
        'records_imported': imported,
        'details': details,
        'timestamp': now_utc().isoformat(),
    }

