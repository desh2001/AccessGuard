"""Dialog Final ML Microservice Client Adapter.

Connects to Hashan's Dialog ML microservice (repo: `Dialog-Project-Final-ML`)
at `ML_SERVICE_URL` (default: http://127.0.0.1:8001) for model inference.

If the external ML microservice is online, predictions are fetched via HTTP.
If offline or unreachable, it gracefully falls back to the local Scikit-Learn
IsolationForest engine with transparent provenance reporting.
"""
from __future__ import annotations
import os
from typing import Any
import httpx
from dotenv import load_dotenv

load_dotenv()

ML_SERVICE_URL = os.getenv('ML_SERVICE_URL', 'http://127.0.0.1:8001').rstrip('/')


def check_external_ml_health() -> dict[str, Any]:
    """Ping the external Dialog Final ML service to verify connectivity."""
    url = f"{ML_SERVICE_URL}/health"
    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
                return {
                    'online': True,
                    'url': ML_SERVICE_URL,
                    'status': 'connected',
                    'service_name': data.get('service_name', 'Dialog-Project-Final-ML'),
                    'model_version': data.get('model_version', 'v1.0-production'),
                    'algorithm': data.get('algorithm', 'IsolationForest / Risk Scorer'),
                }
    except Exception as e:
        pass

    return {
        'online': False,
        'url': ML_SERVICE_URL,
        'status': 'offline',
        'fallback': 'AccessGuard Built-in IsolationForest Engine',
        'message': f"External ML service at {ML_SERVICE_URL} is unreachable; falling back to local ML engine.",
    }


def query_external_ml(grant_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Send active entitlement records to the external ML service for scoring."""
    url = f"{ML_SERVICE_URL}/predict-risk"
    active_records = [r for r in grant_rows if r.get('grant_status') == 'Active']
    if not active_records:
        return None

    # Prepare normalized feature payload
    payload = {
        'grants': [
            {
                'grant_id': r['id'],
                'identity_id': r.get('identity_id'),
                'identity_name': r.get('identity_name'),
                'department': r.get('department'),
                'system_id': r.get('system_id'),
                'permission': r.get('permission'),
                'resource': r.get('resource'),
                'privilege': r.get('privilege', 0),
                'cross_department': r.get('cross_department', 0),
                'last_verified_use': r.get('last_verified_use'),
                'rule_score': r.get('risk_score', 0),
            }
            for r in active_records
        ]
    }

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                data['source'] = 'external-dialog-ml'
                data['service_url'] = ML_SERVICE_URL
                return data
    except Exception:
        # Service unreachable; caller falls back to local engine
        return None

    return None

