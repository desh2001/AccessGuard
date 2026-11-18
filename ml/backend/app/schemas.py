from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountFeatureRecord(BaseModel):
    """One technical account's normalized features for one 90-day review window.

    Do not include usernames, email addresses, employee names, raw log lines,
    secrets or ground-truth labels in `features`.
    """
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=80)
    features: dict[str, Any]

    @field_validator("account_id")
    @classmethod
    def trim_account_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("account_id cannot be blank")
        return value

    @field_validator("platform")
    @classmethod
    def trim_platform(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("platform cannot be blank")
        return value


class ScoreAccountsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_id: str = Field(min_length=1, max_length=120)
    window_days: int = Field(default=90, ge=30, le=365)
    records: list[AccountFeatureRecord] = Field(min_length=1, max_length=50000)


class ScoreResult(BaseModel):
    account_id: str
    platform: str
    status: str
    reason: str | None = None
    model_key: str | None = None
    model_schema: str | None = None
    model_trained_utc: str | None = None
    algorithm: str | None = None
    anomaly_percentile_0_1: float | None = None
    anomaly_percentile_100: float | None = None


class ScoreAccountsResponse(BaseModel):
    service: str
    service_version: str
    cycle_id: str
    window_days: int
    total_accounts: int
    scored_accounts: int
    unscored_accounts: int
    model_counts: dict[str, int]
    results: list[ScoreResult]
