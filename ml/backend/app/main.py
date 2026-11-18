from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from .schemas import ScoreAccountsRequest, ScoreAccountsResponse
from .service import (
    SERVICE_NAME,
    SERVICE_VERSION,
    build_model_status,
    load_model_registry,
    score_accounts,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load only existing, integrity-checked artifacts. No training happens here.
    registry, errors = load_model_registry()
    app.state.model_registry = registry
    app.state.model_errors = errors
    yield


app = FastAPI(
    title=SERVICE_NAME,
    version=SERVICE_VERSION,
    description=(
        "Inference-only quarterly access-review scoring service. The main "
        "AccessGuard backend owns identity, evidence, policy and human decisions."
    ),
    lifespan=lifespan,
)


def require_service_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("ML_SERVICE_TOKEN", "").strip()
    if len(expected) < 32:
        raise HTTPException(
            status_code=503,
            detail="ML_SERVICE_TOKEN must be configured with at least 32 characters",
        )
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid ML service credentials")


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    registry = getattr(request.app.state, "model_registry", {})
    return {
        "status": "ok",
        "service_name": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "models_loaded": len(registry),
        "note": "Liveness only; inspect /v1/models for trained model readiness.",
    }


@app.get("/v1/ready")
def ready(request: Request) -> dict[str, Any]:
    registry = getattr(request.app.state, "model_registry", {})
    errors = getattr(request.app.state, "model_errors", {})
    result = build_model_status(registry, errors)
    if not result["all_models_loaded"]:
        raise HTTPException(status_code=503, detail=result)
    return {"status": "ready", **result}


@app.get("/v1/models")
def models(request: Request) -> dict[str, Any]:
    registry = getattr(request.app.state, "model_registry", {})
    errors = getattr(request.app.state, "model_errors", {})
    return build_model_status(registry, errors)


@app.post(
    "/v1/score/accounts",
    response_model=ScoreAccountsResponse,
    dependencies=[Depends(require_service_token)],
)
def score_account_batch(payload: ScoreAccountsRequest, request: Request) -> dict[str, Any]:
    account_ids = [record.account_id for record in payload.records]
    if len(account_ids) != len(set(account_ids)):
        raise HTTPException(status_code=422, detail="account_id must be unique within one cycle batch")

    registry = getattr(request.app.state, "model_registry", {})
    errors = getattr(request.app.state, "model_errors", {})
    records = [record.model_dump() for record in payload.records]
    results = score_accounts(records, payload.window_days, registry, errors)
    counts = {
        platform: sum(
            1 for item in results
            if item.get("status") == "scored" and item.get("model_key") == platform
        )
        for platform in ("windows", "linux", "github")
    }
    scored = sum(item.get("status") == "scored" for item in results)
    return {
        "service": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "cycle_id": payload.cycle_id,
        "window_days": payload.window_days,
        "total_accounts": len(results),
        "scored_accounts": scored,
        "unscored_accounts": len(results) - scored,
        "model_counts": counts,
        "results": results,
    }
