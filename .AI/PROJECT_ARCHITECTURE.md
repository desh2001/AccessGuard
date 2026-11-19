# Project Architecture — AccessGuard Complete Research Lab

## 1. System Vision & Paradigm

**AccessGuard** is an open, local-first research platform engineered for **AI-assisted Identity Governance and Administration (IGA)**. 

In enterprise environments, organizations face **"Access Creep"** (privilege accumulation as employees switch roles or projects), orphaned accounts (active credentials belonging to departed contractors or forgotten services), toxic entitlement combinations (Separation of Duties conflicts), and unmonitored administrative sprawl. 

Traditional IGA systems either rely on rigid static role definitions that become outdated instantly, or black-box algorithmic certifiers that risk business interruption. AccessGuard enforces **transparent hybrid governance**:
1. Deterministic, explainable policy rules evaluate mandatory lifecycle transitions (leaver holding access, internal transfers, unlinked accounts).
2. Unsupervised Isolation Forest models score behavioral and entitlement divergence per platform.
3. Strict human-in-the-loop review authority makes all access decisions (retain, revoke-request, reduce-access-request).
4. Full audit trail and simulated remediation protect operational integrity.

---

## 2. High-Level Ecosystem Topology

The AccessGuard architecture maintains clean separation of concerns:
- **Root Frontend (`frontend/`):** React 19 + Tailwind CSS single page application. Serves as the sole UI for inventory, risk, and quarterly account reviews.
- **Root Backend (`backend/`):** FastAPI application on port `8000`. Acts as the single system of record, owning database entities, connector ingestion, account identity resolution, 90-day feature construction, policy rules, and review workflows.
- **ML Microservice (`ml/backend/`):** Pure inference microservice on port `8001`. Loads 3 pre-trained platform models (Windows, Linux, GitHub) and returns anomaly percentiles. It contains **no frontend, no database, and no in-batch model fitting**.

```mermaid
flowchart TD
    subgraph Client ["Client Presentation Layer"]
        Browser["User Web Browser\n(http://127.0.0.1:5173)"]
    end

    subgraph CorePlatform ["AccessGuard Core Platform"]
        Vite["Vite Dev Server / Proxy\n(:5173)"]
        Backend["FastAPI Core Backend (:8000)\n- Identity Correlation Engine\n- Deterministic Policy Rules\n- 90-Day Feature Aggregator\n- Quarterly Review Orchestrator\n- CSV Import / Preview / Commit\n- Simulated Remediation"]
        Postgres[("PostgreSQL 17 Database\nContainer Port: 5432\nHost Port: 5434\nDatabase: accessguard_lab")]
    end

    subgraph IngestionSubsystem ["Dialog Access Log Subsystem (accesslog-main)"]
        SyslogCollector["TCP Syslog Collector (:5514)\n- RFC 3164 / 5424 Listener"]
        AccessLogAPI["Log Explorer API (:8002)\n- Device & Event Explorer"]
        FTPServer["FTP Spool / Local Ingest (/incoming_logs)"]
        SentinelCloud["Universal Ingestion API\n(host.pasinduudana.me)"]
    end

    subgraph MLMicroservice ["AccessGuard Quarterly ML Microservice (ml/backend)"]
        MLService["Aegis V9 Inference Service (:8001)\n- Windows AD Model\n- Linux Host Model\n- GitHub SaaS Model\n- Bearer Token Auth"]
        Artifacts[("Joblib Artifacts &\nSHA-256 Manifests\n(ml_artifacts/platforms/)")]
    end

    Browser -->|HTTP / SPA| Vite
    Vite -->|Reverse Proxy /api| Backend
    Backend -->|SQLAlchemy 2.0 / psycopg| Postgres

    SyslogCollector -->|Raw Syslog Packets| AccessLogAPI
    AccessLogAPI -->|Device Telemetry| Backend
    Backend -->|Log Ingestion Sync| FTPServer
    AccessLogAPI -.->|Remote Ingestion| SentinelCloud

    Backend -->|POST /v1/score/accounts\n(Opaque account_ids + features)| MLService
    MLService -->|Read-only inference| Artifacts
    MLService -->|Anomaly Percentiles\n(Join by account_id)| Backend
```

---

## 3. Component Deep Dive

### 3.1. Identity Correlation & Evidence Linkage (`backend/accesslog_client.py`)
- **Deterministic Identifier Matching:** Resolves raw events to technical accounts via:
  1. Windows SID (`Account.native_id` where `native_id_type='sid'`)
  2. Linux UID (`Account.native_id` where `native_id_type='uid'`)
  3. GitHub Numeric ID (`Account.native_id` where `native_id_type='github_id'`)
  4. Scoped username/email matching.
- **Quarantine Isolation:** Unmatched or ambiguous events are logged directly into `activity_quarantine` table with reason codes (`no_matching_account`, `ambiguous_account_match`). They are **never** attributed to an arbitrary account.
- **Deduplication:** Enforces unique constraint on `(source, source_event_id)` to prevent replay attacks and duplicate evidence counting.

### 3.2. 90-Day Feature Builder (`backend/quarterly_feature_builder.py`)
- Builds exactly one feature vector per active technical account for the review window.
- Calculates verified activity days, distinct resources, and 3-month cadence ($M_1, M_2, M_3$).
- Validates telemetry coverage via `activity_coverage`. If coverage is missing or $< 99.5\%$, `log_coverage_known` is set to `0`.

### 3.3. Aegis V9 ML Service (`ml/backend/app/main.py`)
- Independent FastAPI service listening on `http://127.0.0.1:8001`.
- Enforces Bearer token authentication via `ML_SERVICE_TOKEN` ($\ge 32$ chars).
- Exposes:
  - `GET /health`: Service liveness.
  - `GET /v1/models`: Real evaluation metrics, feature counts, and loaded status of the 3 models.
  - `GET /v1/ready`: Returns 200 ready only when all 3 models are verified and loaded.
  - `POST /v1/score/accounts`: Batch inference returning anomaly percentiles joined by `account_id`.

### 3.4. Quarterly Review Service (`backend/quarterly_review_service.py`)
- **Cycle Lifecycle:** Preview $\rightarrow$ Create (freeze population and snapshot features) $\rightarrow$ Review tasks.
- **Budgeting & Policies:** Mandatory overrides for leavers, transfers, and unlinked accounts; budget selection for high-risk accounts; preservation of spare review budget.
- **CSV Workflow:** Generates UTF-8 BOM template, previews uploaded CSV files, validates row schema and business logic, and executes atomic batch commits to `quarterly_review_outcomes`.
- **Training Readiness:** Tracks `verified_normal` vs `confirmed_behavioral_concern` outcomes and exports frozen training candidate snapshots.

### 3.5. Root Frontend Interface (`frontend/src/App.jsx`)
- Single, responsive React 19 UI styled with Tailwind CSS.
- **Quarterly Account Reviews Pane:**
  - **Review Queue:** High-priority and mandatory tasks with natural language policy explanations and ML percentiles.
  - **Reviewed CSV Workflow:** Export template button, drag-and-drop CSV upload, validation error preview modal, and atomic commit submission.
  - **Model Training Readiness:** Real-time progress bars towards training threshold ($N \ge 120$) and candidate dataset export button.
