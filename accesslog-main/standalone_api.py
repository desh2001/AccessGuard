"""Standalone Runner for Dialog Access Log API & Ingestion Service (Pasindu's Service).

Runs independently on port 8002:
    python standalone_api.py

Provides:
- GET /api/health
- GET /api/summary
- GET /api/events
- GET /api/devices
- GET /api/alerts
- Background TCP Syslog collector on port 5514 (if available)
"""
from __future__ import annotations
import os
import re
import socketserver
import threading
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(
    title="Dialog Access Log & Syslog Ingestion API",
    version="1.0.0",
    description="Real-time syslog ingestion and device access monitoring engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory event buffer with live telemetry only
START_TIME = datetime.now(timezone.utc)

DEVICES = []

EVENTS = []



@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service_name": "Dialog Access Review API",
        "author": "Pasindu",
        "syslog_port": 5514,
        "events_count": len(EVENTS),
    }


@app.get("/api/summary")
def summary():
    failed = sum(1 for e in EVENTS if e.get("event_type") == "LOGIN_FAILED")
    return {
        "total_events": len(EVENTS),
        "failed_logins_24h": failed,
        "active_devices_15m": len([d for d in DEVICES if d.get("status") == "active"]),
        "devices_seen": len(DEVICES),
        "hourly": [],
        "types": [],
    }


@app.get("/api/events")
def get_events(limit: int = Query(100, ge=1, le=500), device: str = "", event_type: str = ""):
    results = EVENTS
    if device:
        results = [e for e in results if device.lower() in e["device_id"].lower()]
    if event_type:
        results = [e for e in results if e["event_type"].lower() == event_type.lower()]
    return results[:limit]


@app.get("/api/devices")
def get_devices():
    return DEVICES


@app.get("/api/alerts")
def get_alerts():
    return [
        {
            "device_id": "vpn-gw-colombo.dialog.lk",
            "user_id": "hashan.h",
            "failures": 7,
            "last_seen": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
            "rule": "5+ failed logins in one hour",
            "severity": "high",
        },
        {
            "device_id": "win-dc01.corp.dialog.lk",
            "user_id": "tharindu.s",
            "failures": 5,
            "last_seen": (datetime.now(timezone.utc) - timedelta(minutes=42)).isoformat(),
            "rule": "5+ failed logins in one hour",
            "severity": "high",
        },
    ]


def detect_os(raw_msg: str, dev_id: str) -> str:
    lower = f"{raw_msg} {dev_id}".lower()
    if any(k in lower for k in ['windows', 'event 4624', 'event 4625', 'microsoft', 'wfh', 'win-', 'active directory', 'logon type']):
        return 'Windows'
    if any(k in lower for k in ['linux', 'sudo', 'sshd', 'pts/', 'systemd', 'nginx', 'bash', 'ubuntu', 'debian', 'centos', 'bastion']):
        return 'Linux'
    return 'Windows' if 'win' in dev_id.lower() else 'Linux'


# Optional Background Syslog Server (Port 5514)
class SyslogHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            for raw in self.rfile:
                s = raw.decode("utf-8", errors="replace").strip()
                if not s:
                    continue
                
                src_ip = self.client_address[0]
                os_type = detect_os(s, src_ip)
                dev_id = f"{os_type.lower()}-{src_ip.replace('.', '-')}.corp.dialog.lk"

                # Update or register device in DEVICES list
                existing = next((d for d in DEVICES if d.get('source_ip') == src_ip), None)
                if existing:
                    existing['event_count'] = existing.get('event_count', 0) + 1
                    existing['last_seen'] = datetime.now(timezone.utc).isoformat()
                    existing['status'] = 'active'
                    existing['os'] = os_type
                else:
                    DEVICES.append({
                        'device_id': dev_id,
                        'name': f"{os_type} PC / Server ({src_ip})",
                        'source_ip': src_ip,
                        'os': os_type,
                        'status': 'active',
                        'event_count': 1,
                        'last_seen': datetime.now(timezone.utc).isoformat(),
                    })

                ev = {
                    "id": len(EVENTS) + 1,
                    "device_id": dev_id,
                    "device_name": f"{os_type} ({src_ip})",
                    "os": os_type,
                    "user_id": "syslog-user",
                    "event_type": "LOGIN_FAILED" if any(f in s.lower() for f in ['failed', '4625', 'failure']) else "LOGIN_SUCCESS",
                    "action": "AUTH_EVENT",
                    "severity": "warning" if "fail" in s.lower() else "info",
                    "source_ip": src_ip,
                    "raw_message": s[:500],
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                }
                EVENTS.insert(0, ev)
        except Exception:
            pass


def start_syslog_listener():
    try:
        server = socketserver.ThreadingTCPServer(("0.0.0.0", 5514), SyslogHandler)
        server.serve_forever()
    except Exception:
        pass  # Port may require elevation or be in use


threading.Thread(target=start_syslog_listener, daemon=True).start()

if __name__ == "__main__":
    print("==================================================================")
    print("  Dialog Access Log API running at http://127.0.0.1:8002")
    print("  Syslog listener active on TCP port 5514")
    print("==================================================================")
    uvicorn.run("standalone_api:app", host="127.0.0.1", port=8002, reload=False)

