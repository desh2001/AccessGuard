# Aegis V8 – Independent Windows, Linux and GitHub ML Models

## What changed from V7

V7 used one shared quarterly Isolation Forest for every platform. V8 replaces the **runtime quarterly model** with three independent trained Isolation Forest pipelines: Windows, Linux, and GitHub. Each has a separate training population, feature selection, preprocessing, anomaly reference distribution, evaluation, saved artifact and SHA-256 integrity manifest; optional HMAC signing uses `AEGIS_MODEL_SIGNING_KEY`. The legacy shared-model code remains only for migration/regression tests and is not loaded by the review API.

| Model | Selected input features | Special optional signal | Source artifact |
|---|---|---|---|
| Windows | 90-day login/resource usage, privileges, permissions, dated AD group information, manager/department changes | normalized Windows privileged logons (e.g., 4672, not misuse proof) | `backend/ml_artifacts/platforms/windows.joblib` |
| Linux | 90-day activity, privileges, Linux permission/usage patterns, transfers, selected AD context | normalized audited sudo activity | `backend/ml_artifacts/platforms/linux.joblib` |
| GitHub | 90-day repository-associated use, privilege/entitlement changes, active days, transfer context | normalized attributable GitHub repo audit activity | `backend/ml_artifacts/platforms/github.joblib` |

**Important:** These are source-specific *account-level feature models*, not natural-language/raw-log parsers or real-time EDR detectors. The log-collection teammate must parse the actual event sources and provide normalized authoritative data, and the API teammate must link identities, entitlements and reviews. Source availability and completeness must be checked.

## Data flow

```
Windows logs + AD ──> normalizer ──> PostgreSQL ──> Windows 90-day features ──> Windows IF ─┐
Linux SSH/audit logs ─> normalizer -> PostgreSQL -> Linux 90-day features ──────> Linux IF ───┤
GitHub API/audit ─────> normalizer -> PostgreSQL -> GitHub 90-day features ─────> GitHub IF ──┤
HR status / transfers / governed AD groups ──> mandatory policy review engine ──────────────┤
                                                                                             ▼
                            One prioritized access-review queue -> system owner human decision
```

The platform router accepts explicit variants (Windows AD, Linux, GitHub Enterprise). It does **not** map GitLab to GitHub and does not use a different platform's trained model as a fallback. Accounts without sufficiently attested resource-use coverage or without a trained source model remain unscored; mandatory lifecycle cases remain mandatory regardless. Unscored accounts still receive policy-based review analysis, with unresolved evidence gaps tracked separately.

## Run

From the `backend` folder after installing `requirements.txt`:

```bash
python -m app.ml.periodic_generate --rows 1800 --out ml_data/periodic_synthetic.csv
python -m app.ml.platform_train --csv ml_data/periodic_synthetic.csv
python -m app.ml.platform_benchmark --csv ml_data/periodic_synthetic.csv --budget 10
python -m app.ml.competition_demo --accounts 1200 --budget 10 --with-ml
python -m pytest -q
```

Or use `docker compose up --build` from the project root after setting strong credentials in `.env`. `backend/ml_artifacts` is mounted into the backend container. Review via **90-Day Review AI** and `POST /api/review-cycles/preview` with `window_days:90`. The preview now returns `platform_model_loaded`, `platform_model_scored` and per-account `ml_model_key`/`ml_model_version`. `GET /api/ml/status` exposes independent platform artifact availability. The saved review evidence includes the model key and schema version for each selected account.

## Training/evaluation integrity

- Training **fits each model separately** using known-normal records (a provisional semi-supervised baseline); `group_id` is used for an account-grouped 75%/25% split, never as a predictive feature.
- Held-out labels in the shipped CSV are **fictional and not validated enterprise access-removal decisions**. Per-model ROC AUC / average precision are only a smoke test of the synthetic simulation.
- Risk and authorization policy controls are separate from novelty detection. A rare account is not necessarily problematic, and ordinary music/browsing must not be treated as unauthorized managed-resource use.
- Model output is a *reference rarity percentile*, not an inappropriate-access probability. Different platform percentiles may not be equally calibrated on real populations. Validate per-platform precision, recall, false negatives, missed high/critical cases and reviewer minutes with a blind parallel manual-review pilot.
- For the pilot, let the model score **all accounts**. After freezing the scores, use independent manual decisions as ground truth. Model shortlist does not override company-mandated full review, open transfer obligations or a reviewer decision.
- The operational queue is a maximum budget for nonmandatory candidates, not a guaranteed reduction. Never certify unselected accounts automatically.
- Only deploy locally for demo: current code lacks live enterprise-scale identity and event connectors, account-level entitlement coverage attestations, multi-tenant isolation, secure provenance end-to-end, cross-platform anomaly calibration and PostgreSQL load testing. Three trained models **do not automatically guarantee better accuracy**.

## Handoff to teammates

**Log teammate:** map source-native events to supported normalized names; provide account id, platform, timestamp, result, resource, evidence source, coverage attestations, authoritative entitlement inventory. Windows 4672 and Linux sudo events are contextual only; resource-use evidence is stricter. Avoid monitoring general personal browsing.

**API teammate:** keep source platform and account identity stable, retain HR transfer obligations, load/save cycle model key/version, show platform-specific evidence in dashboard, never revoke upstream access without reviewed approval, store blinded full-manual outcomes for pilots.

**ML teammate:** train three models, compare them to rules-only on separate holdouts, monitor coverage and source drift, check cross-platform calibration, and adjust thresholds only after pilot A and untouched pilot B.

## Current V8 verification results (November 2026)

- Backend: 53 automated tests passed, including the 3-platform SQL-to-queue integration test, mandatory-transfer preservation, wrong-platform rejection, coverage handling, model artifact integrity and ordinary-browsing exclusion.
- Three separate synthetic-trained model artifacts were produced. Synthetic held-out AUCs were approximately Windows 0.920, Linux 0.949, GitHub 0.969, **not real operational accuracy**.
- At a 20% synthetic review budget, rules-only recall was 0.7848 and 3-model hybrid recall was 0.7595. Therefore the hybrid **did not outperform** the policy baseline in that particular experiment. More models are not automatically better; calibrate against independent human decisions.
- An 80,000 fictional-account **in-memory ranking exercise** completed in approximately 2.3 seconds in this environment. It did not test PostgreSQL import/queries, identity mapping, complete 90-day event collection, model retraining, API concurrency or reviewer workflows; it is not a production performance claim.
- The React screen passed a TSX parser/transpilation syntax check; a complete npm production build was not verified here.

**Migration from V7:** re-generate platform-specific features, re-train with `python -m app.ml.platform_train`, and confirm all three models in `/api/ml/status`. V7's `periodic_review_model.joblib` is intentionally not used by the V8 periodic API. Preserve historical review evidence; do not replace signed pilot A outcomes with newly scored models without running a new pilot.
