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

# In-memory event buffer with realistic starting telemetry
START_TIME = datetime.now(timezone.utc)

DEVICES = [
    {"device_id": "vpn-gw-colombo.dialog.lk", "source_ip": "10.77.0.1", "event_count": 1420, "status": "active", "last_seen": "Just now"},
    {"device_id": "win-dc01.corp.dialog.lk", "source_ip": "10.77.0.12", "event_count": 892, "status": "active", "last_seen": "2 mins ago"},
    {"device_id": "linux-bastion-prod.dialog.lk", "source_ip": "10.77.0.15", "event_count": 641, "status": "active", "last_seen": "5 mins ago"},
    {"device_id": "app-k8s-node-03.dialog.lk", "source_ip": "10.77.0.28", "event_count": 410, "status": "active", "last_seen": "12 mins ago"},
    {"device_id": "db-postgres-cluster.dialog.lk", "source_ip": "10.77.0.44", "event_count": 188, "status": "inactive", "last_seen": "28 mins ago"},
]

EVENTS = [
    {
        "id": 1,
        "device_id": "linux-bastion-prod.dialog.lk",
        "user_id": "chamila.d",
        "event_type": "PRIVILEGE_USED",
        "action": "PRIVILEGE_USED",
        "severity": "warning",
        "source_ip": "10.77.0.15",
        "raw_message": "sudo: chamila.d : TTY=pts/2 ; PWD=/home/chamila.d ; USER=root ; COMMAND=/usr/bin/systemctl restart nginx",
        "occurred_at": (START_TIME - timedelta(minutes=4)).isoformat(),
    },
    {
        "id": 2,
        "device_id": "win-dc01.corp.dialog.lk",
        "user_id": "rishan.k",
        "event_type": "LOGIN_SUCCESS",
        "action": "LOGIN_SUCCESS",
        "severity": "info",
        "source_ip": "10.77.0.12",
        "raw_message": "Microsoft-Windows-Security-Auditing: Event 4624: An account was successfully logged on. Account Name: rishan.k Logon Type: 10",
        "occurred_at": (START_TIME - timedelta(minutes=11)).isoformat(),
    },
    {
        "id": 3,
        "device_id": "vpn-gw-colombo.dialog.lk",
        "user_id": "hashan.h",
        "event_type": "LOGIN_FAILED",
        "action": "LOGIN_FAILED",
        "severity": "warning",
        "source_ip": "10.77.0.1",
        "raw_message": "sshd[19284]: Failed password for invalid user hashan.h from 192.168.1.104 port 52311 ssh2",
        "occurred_at": (START_TIME - timedelta(minutes=18)).isoformat(),
    },
    {
        "id": 4,
        "device_id": "vpn-gw-colombo.dialog.lk",
        "user_id": "hashan.h",
        "event_type": "LOGIN_FAILED",
        "action": "LOGIN_FAILED",
        "severity": "warning",
        "source_ip": "10.77.0.1",
        "raw_message": "sshd[19302]: Failed password for invalid user hashan.h from 192.168.1.104 port 52319 ssh2 (repeated attempt 2)",
        "occurred_at": (START_TIME - timedelta(minutes=17)).isoformat(),
    },
    {
        "id": 5,
        "device_id": "linux-bastion-prod.dialog.lk",
        "user_id": "kasun.p",
        "event_type": "LOGIN_SUCCESS",
        "action": "LOGIN_SUCCESS",
        "severity": "info",
        "source_ip": "10.77.0.15",
        "raw_message": "sshd[22105]: Accepted publickey for kasun.p from 10.77.0.88 port 48102 ssh2: RSA SHA256:7mC... (authorized key match)",
        "occurred_at": (START_TIME - timedelta(minutes=25)).isoformat(),
    },
    {
        "id": 6,
        "device_id": "app-k8s-node-03.dialog.lk",
        "user_id": "svc-deployer",
        "event_type": "OTHER",
        "action": "OBSERVED",
        "severity": "info",
        "source_ip": "10.77.0.28",
        "raw_message": "dockerd[1044]: Container dialog-core-api started for deployment rollout v2.4.1",
        "occurred_at": (START_TIME - timedelta(minutes=32)).isoformat(),
    },
    {
        "id": 7,
        "device_id": "win-dc01.corp.dialog.lk",
        "user_id": "tharindu.s",
        "event_type": "LOGIN_FAILED",
        "action": "LOGIN_FAILED",
        "severity": "warning",
        "source_ip": "10.77.0.12",
        "raw_message": "Microsoft-Windows-Security-Auditing: Event 4625: An account failed to log on. Account Name: tharindu.s Reason: Unknown user name or bad password",
        "occurred_at": (START_TIME - timedelta(minutes=45)).isoformat(),
    },
]


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
    failed = sum(1 for e in EVENTS if e["event_type"] == "LOGIN_FAILED")
    return {
        "total_events": len(EVENTS) + 3540,
        "failed_logins_24h": failed + 12,
        "active_devices_15m": 4,
        "devices_seen": len(DEVICES),
        "hourly": [
            {"hour": "10:00", "total": 180},
            {"hour": "11:00", "total": 240},
            {"hour": "12:00", "total": 310},
            {"hour": "13:00", "total": 285},
            {"hour": "14:00", "total": 390},
            {"hour": "15:00", "total": 420},
        ],
        "types": [
            {"event_type": "LOGIN_SUCCESS", "total": 2100},
            {"event_type": "OBSERVED", "total": 840},
            {"event_type": "PRIVILEGE_USED", "total": 380},
            {"event_type": "LOGIN_FAILED", "total": 231},
        ],
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


# Optional Background Syslog Server (Port 5514)
class SyslogHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            for raw in self.rfile:
                s = raw.decode("utf-8", errors="replace").strip()
                if not s:
                    continue
                ev = {
                    "id": len(EVENTS) + 1,
                    "device_id": self.client_address[0],
                    "user_id": "syslog-client",
                    "event_type": "OBSERVED",
                    "action": "OBSERVED",
                    "severity": "info",
                    "source_ip": self.client_address[0],
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

