# Root AccessGuard ↔ Quarterly ML Service Contract

## Ownership boundary

The root AccessGuard backend owns persistence, canonical identity resolution, normalized raw event data, 90-day aggregation, organization policy, quarterly cycles, reviewer assignment, human decisions and audit history.

This `ml/` service owns the three trained platform pipelines, feature-schema validation, model artifact integrity checks and anomaly percentile inference only. It has no frontend and no business database.

## Endpoint

`POST /v1/score/accounts`

Headers:

```http
Authorization: Bearer <ML_SERVICE_TOKEN>
Content-Type: application/json
```

Body:

```json
{
  "cycle_id": "2026-Q4",
  "window_days": 90,
  "records": [
    {
      "account_id": "<opaque-root-account-id>",
      "platform": "Windows AD | Linux | GitHub",
      "features": { "<model feature>" : "<numeric or categorical value>" }
    }
  ]
}
```

`account_id` is the root database's stable opaque technical-account identifier, not a username. One record per account per review cycle. A record is not one event and not one entitlement.

## Feature schema source of truth

The exact required schema is maintained in:

- `backend/app/ml/platforms/windows.py`
- `backend/app/ml/platforms/linux.py`
- `backend/app/ml/platforms/github.py`

The root feature builder must read/use these definitions or keep an automated schema-contract test against them. Do not maintain a divergent duplicate list in `backend/main.py`.

The scoring API additionally requires:

- `window_days == 90`;
- `log_coverage_known == 1`;
- `log_coverage_days >= 89.55` (99.5% of 90 days).

The two source-specific event count/coverage flags are optional for structural schema validation but should be supplied from the real source connector. Missing feed coverage must remain unknown. Do not synthesize `1`.

## Data that must never be in model features

Do not send usernames, emails, employee names, manager names, raw IP addresses, raw log messages, passwords, API tokens, account/employee identifiers, `group_id`, training `label`, review decision or ground-truth labels inside `features`. `account_id` is a separate opaque correlation field and is echoed in the response only.

## Response semantics

The response has exactly one result for every request record, in request order. The root backend must map results by `account_id`, never by array position.

`anomaly_percentile_0_1` is a relative percentile between 0 and 1. `anomaly_percentile_100` is the same percentile expressed from 0 to 100. Neither is a probability or proof of unauthorized access.

Unscored results must remain explicitly unscored. Never convert a null anomaly score to zero or a low risk level. Use a separate `policy_only` provenance when deterministic rules produced the queue without a trained model.

## No model fallback during inference

If a model file is missing, invalid, or unsupported, that platform is unscored. Do not dynamically fit Isolation Forest on the current request, current cohort or batch. Do not route GitLab or unknown platforms into another model. The policy queue and mandatory human reviews must still function without ML.

## Policy ownership

The service does not resolve user identity, classify an AD group, determine resource authorization, detect HR transfer obligations, create review tasks, decide retain/revoke, or mutate permissions. These are root backend responsibilities. Internal transfers and other mandatory lifecycle/policy triggers always bypass the ML score and review-budget cap.
