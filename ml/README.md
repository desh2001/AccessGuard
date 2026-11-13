# Aegis V8 – Separate Windows, Linux & GitHub ML Models (Competition)

**Start here:** [V8 three-platform ML guide](V8_THREE_PLATFORM_MODELS_GUIDE.md) · [Collector input schema](sample-data/platform-ml-v8/README.md) · [Expert-reviewed V7 controls](V7_USER_CONCERNS_AND_PLAN.md).

V8 now has **three independent quarterly Isolation Forest models** (Windows, Linux, GitHub), each trained and saved separately. One policy-driven human access-review queue combines their advisory anomaly signals, with mandatory employee-transfer/HR reviews never suppressed. Missing telemetry is not inactivity evidence. GitLab is not silently scored with the GitHub model. The source-native log parsers are integrations for the log teammate; V8 expects normalized data, not raw log text. Models are trained on **synthetic demo data**, not validated enterprise labels, and no account or permission is automatically revoked or certified.

Run from `backend`: `python -m app.ml.periodic_generate --rows 1800`, then `python -m app.ml.platform_train`, then `python -m app.ml.platform_benchmark --budget 10`. Run full app with `docker compose up --build` after configuring `.env`.

**Verification:** See test output in your own environment (`python -m pytest -q`); frontend build requires installed node dependencies. No live enterprise load/accuracy claims.

---

# Aegis V6 — Enterprise-Oriented Access-Review ML (Competition)

**Start here:** [V6 implementation and runbook](ENTERPRISE_ML_V6_GUIDE.md) · [ML data contract](ML_DATA_CONTRACT_V6.md) · [Expert-feedback audit](V6_EXPERT_FEEDBACK_IMPLEMENTATION.md) · [Enterprise readiness gaps](ENTERPRISE_READINESS_CHECKLIST.md).

V6 is built around the industry expert's actual problem: periodic, evidence-aware account review prioritization, **not** real-time EDR anomaly alerts. Company-specific AD group meanings are owned by an approved catalog; **all unreviewed employee transfers are mandatory-review cases**; and a separate blinded full-manual pilot measures missed cases before any thresholds are proposed for a future cycle. Isolation Forest remains advisory, and no account is automatically revoked or certified.

**Verification:** 41 Python backend tests passed, Alembic V5-to-V6 migration was exercised against an isolated SQLite V5 fixture, 80,000 fictional accounts were scored/ranked in memory, and frontend TypeScript/JSX syntax compiled. **This is not a production enterprise deployment.** No live AD connection, real enterprise data validation, real MySQL test, or production DB throughput/latency benchmark is claimed.

The older V3/V4/V5 documents below are historical reference material; V6 documents above supersede them.

---

# V5 — Industry Expert Feedback Update (7 November 2026)

**Start here:** [V5 expert changes](V5_EXPERT_FEEDBACK_CHANGES.md) · [V5 ML run guide](V5_RUN_GUIDE.md). The ML model now uses AD reporting history, internal transfers and AD group evidence; accepts CSV or read-only MySQL source tables; and supports a frozen-ML versus full-manual parallel pilot with adjustable thresholds. Previous V4 docs are retained for historical context; V5 docs take precedence where they differ.

---

# Aegis V4 — Competition Access Review Optimizer

**Current guide (2026-11-07):** First read [`EXPERT_REQUIREMENTS_AUDIT_V4.md`](EXPERT_REQUIREMENTS_AUDIT_V4.md) and [`ML_V4_RUN_GUIDE.md`](ML_V4_RUN_GUIDE.md). They supersede older V2/V3 ML discussion. This is a competition prototype; there is no guarantee of safe automatic certification, validated ML improvement, or live upstream revocation.

**Not a real-time anomaly alert engine.** V4 triages periodic account certification using historical use and entitlement evidence, HR facts, a policy-first shortlist, and optional Isolation Forest anomalies. The illustrative three-account scenario does not define project scope.

---

# Aegis — 90-Day Access Review Optimizer (Competition Edition V3)

**Start with [COMPETITION_ML_CHANGES.md](COMPETITION_ML_CHANGES.md).** This is a competition software prototype, not a university research submission. It follows the industry expert's goal: use 90-day access data to prioritize *account-level* periodic certification by a human, instead of real-time security alarms.

For the demonstration, open **90-Day Review AI** from the dashboard after running `docker compose up --build` with configured `.env` credentials. The project includes fictional Chamila/Rishan/third-account examples, a quarterly Isolation Forest, an explainable policy queue, persistent account-level human reviews, and simulation-only remediation.

> **Limitations:** All included training/demo data are synthetic. No live removal, enterprise-scale ingestion, or validated review savings are implemented. Unselected accounts are not certified as safe. A rules-only baseline currently performs as well as or better than the hybrid on synthetic labels.

---

# Aegis — Intelligent User Access Governance (University MVP)

A runnable full-stack prototype for **user access governance**, not employee surveillance. It inventories permissions, estimates review priority, records human access-review decisions, simulates revocation, and produces review evidence reports.

> **Security boundary:** No live enterprise access is removed. `Simulate revocation` leaves the actual entitlement marked active and records `upstream_changed: false` and `verified: false`. The system is **not** production-ready IAM, IGA, or compliance software.

## Modules implemented

| Module | Included in MVP |
|---|---|
| Employee identities | Imported employee records and account mapping |
| Access inventory | PostgreSQL employee/account/entitlement storage; import for Windows and Linux; optional read-only GitHub org connector |
| Activity evidence | Import typed activity events; only `resource_use` can update verified use; missing evidence is explicitly unknown |
| AI / risk | Explainable rules; offline-trained, optional Isolation Forest with held-out synthetic demonstration metrics |
| Access reviews | Assign reviews, approve retain/revoke, require review justification, enforce reviewer authorization |
| Remediation | Administrator-only simulation after explicit reviewer approval; **no external changes** |
| Dashboard / audit | Dashboard, filters, risk detail panel, audit events, review CSV export |
| Authentication | JWT, Argon2 password hashes, roles (admin/reviewer), seeded synthetic users |

## Quick start — Docker (recommended)

Requirements: Docker Desktop with Compose, at least 2 GB free RAM.

```bash
cp .env.example .env
# Edit .env. Set distinct strong random values for all passwords and JWT_SECRET.
# Generate JWT_SECRET with: openssl rand -hex 32

docker compose up --build
```

Open **http://localhost:5173** (React UI); **http://localhost:8000/docs** (FastAPI interactive API). Log in as `admin` using `DEMO_ADMIN_PASSWORD` or `reviewer` using `DEMO_REVIEWER_PASSWORD` set in `.env`.

On the first boot with an empty DB, the project seeds **synthetic demo employees and permissions**. Seeds do not re-run when employees already exist. `docker compose down -v` destroys the demo database and all locally stored data.

The provided Compose configuration binds the web UI and API to `127.0.0.1` to avoid exposing this prototype directly to other computers. Use a properly hardened reverse proxy and authentication controls before any remote deployment.

## Without Docker (SQLite development)

In separate terminals:

```bash
# Terminal 1
cd backend
python -m venv .venv
# Activate the virtual environment (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
export JWT_SECRET="$(openssl rand -hex 32)"        # Windows PowerShell: $env:JWT_SECRET = "..."
export DEMO_ADMIN_PASSWORD="your-strong-demo-password"  # PowerShell: $env:DEMO_ADMIN_PASSWORD = "..."
export DEMO_REVIEWER_PASSWORD="another-strong-password"
export SEED_DEMO=true
uvicorn app.main:app --reload

# Terminal 2
cd frontend
npm install
npm run dev
```

SQLite database is created in `backend/access_governance.db` by default. The frontend dev proxy sends `/api` to localhost:8000.

## Demo workflow

1. Log in with the `admin` account. See the overview, high-risk entitlements, and evidence breakdown.
2. Open **Access Inventory** and inspect an entitlement's detailed score. Notice the distinction between verified inactivity and unknown use.
3. Click **Generate reviews** (or **Create risk-based reviews**) to assign current medium/high risk cases.
4. Log in as `reviewer`. Open **Access Reviews**, decide **Retain** or **Approve revocation**, and write a reason.
5. Log in as `admin`. For a revocation-approved case, click **Simulate revocation**. This intentionally does not change any upstream account.
6. Open **Audit Trail** and export a CSV recording decisions and unverified simulation status.
7. For your own synthetic sample data, upload the four CSVs in order from `sample-data/`.

### CSV import contract

* `employees.csv`: `code,name,email,department,job_title,status` plus optional `manager_username`.
* `accounts.csv`: `platform,username,employee_code,status`; optional `last_login,last_login_source`. Blank `employee_code` creates an unmapped account.
* `entitlements.csv`: `platform,username,resource,permission,sensitivity`; optional `source,active,last_used_at,evidence_source`.
* `activities.csv`: `platform,username,resource,event_type,occurred_at,source`. Only `event_type=resource_use` counts as *verified resource use*; normal login is not resource use.

Dates use ISO 8601, preferably `YYYY-MM-DDTHH:MM:SSZ`. Maximum 2 MB / 3000 rows per file. CSV import requires administrator access. Import records are upserted by employee code, platform/username, and account/resource/permission; activity events are appended.

### GitHub (optional)

Supply an organization name and a read-only token to the **backend environment** using `GITHUB_ORG` and `GITHUB_TOKEN` in `.env`, then rebuild/restart backend. Use a fine-grained token/GitHub App with the **minimum** repository metadata and collaborator-read access supported by your organization. The backend calls GitHub's repository listing and collaborators endpoints; both require sufficient permissions and may return `403` if not allowed. It scans only the **first 30 repositories and first 100 collaborators per repository**. This deliberately limited connector is illustrative, **not a complete organization inventory**, and ignores teams, SSO state, inherited grant origins, access expiry, and GitHub audit-log resource use. It **does not delete or change permissions** or mark missing rows inactive. Newly found GitHub logins remain *unmapped* until the appropriate employee mapping is imported using `accounts.csv`.

## Risk scoring (transparent baseline)

Maximum 100 points, scored only against active entitlements:

- Account without verified employee mapping: +40.
- Employee status not active: +45.
- Privileged permission (`admin`, `root`, etc.): +20.
- High/critical sensitivity: +15.
- Resource outside a configured department allowlist: +25.
- Verified last resource use 60–89 days ago: +10; 90+ days: +25.
- Account last login 90+ days ago: +10 (separate from last resource use).
- Isolation Forest anomaly flag: +10 only when a **separately offline-trained trusted model** flags it (exploratory, not operationally validated).

High risk: >=70; medium >=35; low below 35. A missing `last_used_at` means **unknown**, not unused. Department rules are demonstration policy and require organization-specific review. Isolation Forest requires a trained, locally generated model artifact in `backend/ml_artifacts/`. It is trained offline from a separately labeled CSV, not refitted on every risk request. Its anomaly percentiles are **not** threat probabilities. All sensitive decisions are made by a designated reviewer, not automatically by ML.

## API routes

| Method | Endpoint | Permission |
|---|---|---|
| POST | `/api/auth/login` | Public |
| GET | `/api/auth/me` | Logged-in |
| GET | `/api/overview`, `/api/metrics`, `/api/employees`, `/api/accounts`, `/api/entitlements` | Logged-in |
| GET | `/api/reviews` | Admin: all; Reviewer: own |
| GET | `/api/ml/status` | Logged-in |
| POST | `/api/risk/recompute` | Admin |
| POST | `/api/reviews/create` | Admin |
| POST | `/api/reviews/{id}/decision` | Assigned reviewer or admin |
| POST | `/api/reviews/{id}/simulate` | Admin, after revoke approval |
| GET | `/api/audit`, `/api/export/reviews.csv` | Admin |
| GET | `/api/integrations/status` | Logged-in |
| POST | `/api/integrations/import/{dataset}` | Admin |
| POST | `/api/integrations/github/sync` | Admin |

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

Tests also cover ML training, missing-evidence semantics, trustworthy model artifacts, inference integration, and rule-only fallback. See [ML_GUIDE.md](ML_GUIDE.md) for the ML teammate’s full step-by-step workstream and [ML_EVALUATION.md](ML_EVALUATION.md) for an honest policy-vs-ML comparison on synthetic scenarios.

## System architecture

```
CSV Windows/Linux exports    Read-only GitHub REST API
           \                         /
            \                       /
             FastAPI ingestion + normalization
                           |
                        PostgreSQL
        Employee ─ Account ─ Entitlement ─ Activity
                           |
              Rule-based scoring + offline-trained IF
                           |
                   Human access review
                           |
                Approved simulation only
                           |
              Audit evidence + React dashboard
```

## Important limitations and production next steps

**This is a university demonstration, not a secure production deployment.** Before connecting enterprise environments, implement:

1. OIDC/enterprise SSO, short-lived sessions, strong MFA, secure httpOnly cookies, account lifecycle, rotation of secrets, transport TLS, stricter password protections and login rate limiting.
2. Verified least-privilege connector credentials and paginated, scope-complete collection with job queue (Celery + Redis), retry, throttling, checkpoints and stale-record reconciliation.
3. Native Windows/Active Directory/Entra ID and Linux connectors, group nesting, inherited/effective entitlements, service-account classification and source-of-truth identity matching.
4. Multi-step sign-off, different reviewers for exceptional / self-access, segregation-of-duties policies, exception expiry, campaign scheduling and reminders.
5. A remediation adapter with explicit approval, a dry run, restricted scopes, service-specific revocation commands, idempotency, upstream read-back verification, failure recovery, and human rollback.
6. Database schema migrations (Alembic), tenant boundaries, immutable audit/append-only storage, monitoring and performance baselines, data minimization and retention policy.
7. ML validation using labeled risk cases (precision/recall, fairness and false-positive rate); distinguish policy-based findings from statistical outliers.
8. Production CI/CD, security scanning, integration tests, backups and disaster recovery, secrets manager and deployment network restrictions.

### Data privacy

Use fictional or consented data, never upload real employee activity to a public demo. Avoid sensitive behavioral monitoring; limit collection to entitlement inventory and minimal purpose-bound activity evidence. Review legal/privacy obligations and retention rules before deploying.

## ML workstream quick start

The **full ML owner guide** is in `ML_GUIDE.md`. From `backend/` after installing requirements:

```bash
python -m app.ml.train --csv ml_data/synthetic_demo.csv
python -m app.ml.demo
python -m pytest -q
```

Or with the Docker stack running: `docker compose exec backend python -m app.ml.train --csv ml_data/synthetic_demo.csv`, then recompute risk in the admin dashboard. All supplied metrics are **only synthetic classroom demonstrations** and cannot be reported as measured real-world access-risk detection accuracy. Never load untrusted `.joblib` files.

## New supervisor-aligned ML (periodic review v2)

The `ML_PERIODIC_UPDATE.md` guide defines the new research target: **prioritize human access reviews from a 90-day history**, not real-time anomaly alerts. It provides updated ML modules and two new admin API endpoints (`/api/review-cycles/preview` and `/api/review-cycles/create`). Optional `/api/integrations/import/coverage` tracks **attested, not independently verified** resource-use telemetry coverage.

From `backend/`:

```bash
python -m app.ml.periodic_generate
python -m app.ml.periodic_train
python -m app.ml.periodic_benchmark --budget 10
python -m pytest -q
```

**Do not skip certification of the non-selected accounts on the strength of this synthetic demo.** It has not been validated for operational false negatives or enterprise compliance. See the guide for details.

## V7 incremental update (November 2026)

See `V7_USER_CONCERNS_AND_PLAN.md` for the privacy-limited business-resource
policy advisory checks, sampled blind manual validation, manual-review overlap
reconciliation, and distinctions between access reviews and EDR/browsing surveillance.
The main 39-feature Isolation Forest model is unchanged; the new company-policy
check is a separate review-priority signal. All access decisions remain human.
