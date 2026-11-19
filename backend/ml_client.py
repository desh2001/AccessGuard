"""AccessGuard Quarterly ML V9/V10 Client Adapter.

Connects the root backend to the inference-only quarterly ML microservice at
`ML_SERVICE_URL` (default: http://127.0.0.1:8001).

Contract:
- POST /v1/score/accounts (Authorization: Bearer <ML_SERVICE_TOKEN>)
- GET /v1/models (inspect actual model availability and metadata)
- GET /v1/ready (readiness check)
- GET /health (process liveness)

Guarantees:
- Opaque account_id matching (never array-index mapping)
- cycle_id and window_days validation
- No dynamic in-batch model fitting fallback
- No hard-coded ROC-AUCs or fake model sizes
"""
from __future__ import annotations
import os
from typing import Any
import httpx
from dotenv import load_dotenv

load_dotenv()

ML_SERVICE_URL = os.getenv('ML_SERVICE_URL', 'http://127.0.0.1:8001').rstrip('/')
ML_SERVICE_TOKEN = os.getenv('ML_SERVICE_TOKEN', '').strip()
DEFAULT_TIMEOUT = 10.0


def _auth_headers() -> dict[str, str]:
    token = os.getenv('ML_SERVICE_TOKEN', ML_SERVICE_TOKEN)
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    return headers


def check_ml_health() -> dict[str, Any]:
    """Check liveness and actual loaded model status from the ML service."""
    url = f"{ML_SERVICE_URL}/health"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                models_info = get_ml_models()
                return {
                    'online': True,
                    'status': 'connected',
                    'url': ML_SERVICE_URL,
                    'service_name': data.get('service_name', 'AccessGuard Quarterly ML Service'),
                    'service_version': data.get('service_version', '9.0.0'),
                    'models_loaded': data.get('models_loaded', 0),
                    'all_models_loaded': models_info.get('all_models_loaded', False),
                    'models': models_info.get('models', {}),
                    'mode': 'inference_only',
                }
    except Exception:
        pass

    return {
        'online': False,
        'status': 'offline',
        'url': ML_SERVICE_URL,
        'service_name': 'AccessGuard Quarterly ML Service',
        'models_loaded': 0,
        'all_models_loaded': False,
        'models': {},
        'mode': 'ml_unavailable',
        'note': 'ML service unreachable. Quarterly reviews remain available in deterministic policy_only mode.',
    }


def get_ml_models() -> dict[str, Any]:
    """Retrieve actual loaded model states and evaluation metadata from /v1/models."""
    url = f"{ML_SERVICE_URL}/v1/models"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    return {
        'service': 'AccessGuard Quarterly ML Service',
        'models_loaded': 0,
        'all_models_loaded': False,
        'models': {
            'windows': {'loaded': False, 'status': 'offline'},
            'linux': {'loaded': False, 'status': 'offline'},
            'github': {'loaded': False, 'status': 'offline'},
        },
        'inference_policy': 'load-only; no fit/retrain on scoring requests',
    }


def score_accounts_batch(
    cycle_id: str,
    window_days: int,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send one batch of account-level 90-day feature records to the ML service.

    Returns dict mapping account_id -> result dict.
    If the service is offline or errors, returns explicit unscored results
    with reason='ml_unavailable' or 'model_not_trained'.
    """
    if not records:
        return {}

    # Strip any internal metadata keys before sending to ML service
    clean_records = []
    for r in records:
        clean_records.append({
            'account_id': str(r['account_id']),
            'platform': str(r['platform']),
            'features': dict(r['features']),
        })

    payload = {
        'cycle_id': cycle_id,
        'window_days': window_days,
        'records': clean_records,
    }

    url = f"{ML_SERVICE_URL}/v1/score/accounts"
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.post(url, headers=_auth_headers(), json=payload)
            if resp.status_code == 200:
                body = resp.json()
                # Validate cycle_id and window_days match
                if body.get('cycle_id') != cycle_id or body.get('window_days') != window_days:
                    raise ValueError("ML response cycle_id/window_days mismatch")

                results_list = body.get('results', [])
                # Map by opaque account_id, never by array index
                results_by_id = {
                    str(item['account_id']): item
                    for item in results_list
                    if 'account_id' in item
                }
                return results_by_id
            elif resp.status_code == 401:
                reason = "ml_service_unauthorized:invalid_token"
            elif resp.status_code == 503:
                reason = "ml_service_not_ready"
            else:
                reason = f"ml_service_http_error:{resp.status_code}"
    except Exception as exc:
        reason = f"ml_service_offline:{type(exc).__name__}"

    # Return explicit unscored fallback for each submitted account
    return {
        str(r['account_id']): {
            'account_id': str(r['account_id']),
            'platform': str(r['platform']),
            'status': 'unscored',
            'reason': reason,
            'model_key': None,
            'model_schema': None,
            'model_trained_utc': None,
            'algorithm': None,
            'anomaly_percentile_0_1': None,
            'anomaly_percentile_100': None,
        }
        for r in records
    }
