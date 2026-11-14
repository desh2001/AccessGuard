# Feature Implementations — AccessGuard Complete Research Lab

## 1. Overview of Platform Capabilities

AccessGuard implements a multi-layered Identity Governance and Administration (IGA) capability suite. The platform bridges raw infrastructure event streams, enterprise employee directories, and machine learning models to solve complex access risk challenges.

The system is organized into **14 integrated governance modules**:

| # | Feature Module | Primary Functionality | Implementation Files |
|---|---|---|---|
| 1 | **Executive Overview** | Real-time governance KPIs, risk distributions, system footprint, campaign progress. | `frontend/src/App.jsx`, `backend/main.py` (`/api/overview`) |
| 2 | **Canonical Identity Directory** | Master employee registry linking human, machine, and vendor identities across platforms. | `backend/main.py` (`/api/identities`), `models.py` |
| 3 | **Live Devices & Syslog Logs** | Real-time syslog ingestion, active host discovery, event filtering, and Sentinel forwarding. | `accesslog-main/`, `backend/accesslog_client.py`, `backend/main.py` |
| 4 | **Account Mapping Engine** | Technical account correlation, orphaned service account detection, heuristic suggestions. | `backend/main.py` (`/api/accounts`), `models.py` |
| 5 | **Access Inventory Catalog** | Entitlement directory with resource tags, permission scopes, and privilege levels. | `backend/main.py` (`/api/access`), `models.py` |
| 6 | **AI Risk Analysis Engine** | Dual-tier risk evaluation: explainable policy heuristics + Isolation Forest anomaly percentiles. | `backend/risk.py`, `backend/ai_engine.py`, `backend/ml_client.py` |
| 7 | **Access Reviews & Campaigns** | Review campaign generation, human-in-the-loop decisions (Retain, Approve Removal). | `backend/main.py` (`/api/reviews`), `models.py` |
| 8 | **Simulated Remediation** | Safe, local-only permission revocation without destructive remote calls. | `backend/main.py` (`/api/reviews/{id}/simulate-revoke`) |
| 9 | **Activity Evidence Engine** | Correlated authentication logs, failed login analysis, and verification timestamps. | `backend/activity.py`, `backend/main.py` (`/api/activity`) |
| 10 | **Offboarding Governance** | Lingering credential detection for departed employees with batch remediation. | `backend/main.py` (`/api/offboarding`) |
| 11 | **Risk Alerts Feed** | High-severity security alerts (toxic combinations, dormant admin, unmapped access). | `backend/main.py` (`/api/alerts`) |
| 12 | **Integrations Hub** | Health monitoring and diagnostics for Dialog Syslog, Dialog ML, Sentinel, and FTP. | `backend/main.py` (`/api/integrations`, `/api/connectors/*`) |
| 13 | **Immutable Audit Trail** | Chronological compliance ledger tracking all administrator and reviewer actions. | `backend/main.py` (`/api/audit`), `models.py` |
| 14 | **Research Reports & Exports** | Analytical evaluation metrics, PR-AUC, model stats, and CSV/JSON export engine. | `backend/main.py` (`/api/reports/summary`, `/api/metrics`) |

---

## 2. Exhaustive Feature Deep-Dives

### 2.1. Executive Overview Dashboard
- **Purpose:** Gives CISOs, IAM leads, and compliance auditors an instant operational posture snapshot.
- **Metrics Computed:**
  - Total Canonical Identities (Human, Machine, Vendor).
  - Total Discovered Technical Accounts (Active vs. Disabled; Linked vs. Unlinked).
  - Active Entitlements & Risk Distribution (Critical, High, Medium, Low).
  - Review Campaign Velocity (Pending vs. Decided vs. Remediated).
  - Target Connected Systems Breakdown (Active Directory, Linux, GitHub, AWS, etc.).
- **Endpoint:** `GET /api/overview`
- **Visualization:** Recharts doughnut charts and progress bars in `frontend/src/App.jsx`.

### 2.2. Canonical Identity Directory (Master Human/Service Registry)
- **Purpose:** Acts as the Single Source of Truth (SSOT) for organizational entities.
- **Data Properties:** `id` (e.g., `EMP-1001`), `name`, `email`, `department`, `job_title`, `type` (`Human`, `Machine`, `Vendor`), `status` (`Active`, `Departed`), and `manager`.
- **Key Operations:**
  - `GET /api/identities`: List all identities with linked account and entitlement counts.
  - `POST /api/identities`: Provision new canonical identity.
  - `GET /api/identities/{id}`: Detailed profile including full access graph, associated hardware devices, and direct reports.
  - `POST /api/identities/{id}/connect-device`: Associate an ingested device/IP with an employee identity.

### 2.3. Live Devices & Syslog Telemetry Subsystem
- **Purpose:** Bridges raw network traffic and host authentication events to canonical identities.
- **Capabilities:**
  - **Syslog Collector Daemon:** TCP listener on port `5514` ingesting RFC 3164/5424 formatted messages.
  - **Log Normalization:** Parses process names, facility levels, severity, source IP, and target usernames.
  - **Device Discovery:** Tracks communicating network devices by IP, hostname, MAC, and operating system.
  - **Sentinel Universal Ingestion:** Streams generated events to `host.pasinduudana.me` via bearer token.
  - **Bidirectional Correlation:** Matches incoming syslog usernames against AccessGuard `accounts.username`.
- **Endpoints:**
  - `GET /api/accesslog/status`: Syslog daemon health check.
  - `GET /api/accesslog/events`: Ingested authentication event feed.
  - `GET /api/accesslog/devices`: Active communicating endpoints.
  - `POST /api/accesslog/sync`: Ingest external syslog records into local `activity_events`.

### 2.4. Account Mapping & Ownership Resolution Engine
- **Purpose:** Solves the core IGA challenge of **Account Correlation**—determining which physical human or service owns technical credentials (e.g., `s_smith`, `svc-backup`, `admin-sql`).
- **Mechanism:**
  - **Automated Heuristic Matching (`/api/accounts/suggestions`):**
    1. Exact email match (`account_email == identity.email`).
    2. Exact username match (`username == identity.id` or normalized email prefix).
    3. Name similarity / tokenized fuzzy match.
  - **Orphan Account Detection:** Flags technical accounts where `identity_id IS NULL`.
  - **Manual Linking & Unlinking:**
    - `POST /api/accounts/{account_id}/link`: Links account to identity, sets `mapping_method='Manual'`, and logs to audit trail.
    - `POST /api/accounts/{account_id}/unlink`: Delinks account, resets to unmapped state, and logs to audit trail.

### 2.5. Access Inventory & Entitlement Catalog
- **Purpose:** Provides a centralized, searchable inventory of all assigned privileges across all connected systems.
- **Data Attributes:**
  - `permission`: Specific permission name (e.g., `Domain Admin`, `sudoers`, `Repo Admin`, `Billing Read`).
  - `resource`: Target entity (e.g., `Production Domain Controllers`, `/etc/shadow`, `org/payment-service`).
  - `privilege`: Integer flag (`1` for elevated administrative access, `0` for standard user access).
  - `cross_department`: Flag indicating whether access lies outside normal departmental boundaries (e.g., Finance user with AWS Production Access).
  - `last_verified_use`: Timestamp of last observed activity evidence.
  - `status`: Lifecycle state (`Active` or `Revoked`).
- **Endpoint:** `GET /api/access`

### 2.6. AI Risk Analysis Engine (Hybrid Heuristics + Machine Learning)
- **Purpose:** Computes comprehensive risk scores to prioritize risky entitlements for human certification.
- **Scoring Pipeline:**
  1. **Deterministic Rule Score (`backend/risk.py`):**
     - Base score: `10` points.
     - Unlinked / Orphaned account: `+40` points.
     - Departed employee holding access: `+50` points.
     - Administrative privilege flag: `+23` points.
     - Cross-department entitlement: `+23` points.
     - Inactivity >= 90 days: `+23` points (only if telemetry exists).
     - Inactivity 45–89 days: `+9` points.
     - Total score capped at `100`.
  2. **Machine Learning Anomaly Percentile (`backend/ai_engine.py` or Dialog ML `:8001`):**
     - Evaluates 8-dimensional feature vectors using an Isolation Forest ensemble.
     - Computes peer-group divergence (e.g., sole user in Marketing holding root access).
     - Emits a relative anomaly percentile (`0–100%`).
  3. **Blended Priority Formula:**
     $$\text{Combined Priority} = \text{round}(0.70 \times \text{Rule Score} + 0.30 \times \text{ML Anomaly Percentile})$$
  4. **Explainable AI (XAI) Output:**
     - Provides clear, natural-language rationales for every score.
     - Labels evidence quality (`Missing` vs. `Partial`).
- **Endpoint:** `GET /api/ai/summary`

### 2.7. Access Review Campaigns & Human-in-the-Loop Certification
- **Purpose:** Manages the periodic or trigger-based entitlement re-certification workflow required by SOC 2 and ISO 27001.
- **Workflow:**
  1. **Campaign Generation:** Click *"Generate Risk-Based Reviews"* (`POST /api/reviews/generate`). Identifies all active grants exceeding risk thresholds or offboarding violations and generates review tickets.
  2. **Reviewer Evaluation:** Human reviewer inspects evidence, activity timestamps, and XAI explanations in the React UI.
  3. **Decision Execution (`POST /api/reviews/{id}/decision`):**
     - **Retain:** Certifies the entitlement as necessary for business operations (`status='Retained'`).
     - **Approve Removal:** Flags the entitlement for remediation (`status='Approved'`).
  4. **Audit Logging:** Every decision logs reviewer identity, decision timestamp, and rationale.

### 2.8. Non-Destructive Simulated Remediation
- **Purpose:** Demonstrates full remediation lifecycle safely without mutating live production systems.
- **Mechanism:**
  - When an authorized reviewer clicks *"Simulate Revoke"* (`POST /api/reviews/{id}/simulate-revoke`):
    1. Validates that the review ticket is approved for removal.
    2. Updates `access_grants.status` from `'Active'` to `'Revoked'`.
    3. Updates `reviews.status` from `'Approved'` to `'Remediated'`.
    4. Appends a tamper-evident entry to `audit_logs`:
       - Actor: Current Reviewer
       - Action: `SIMULATED_REVOKE`
       - Details: Grants revoked, account updated, target system simulated.
    5. Returns confirmation to the UI, instantly updating all dashboard metrics.

### 2.9. Activity Evidence & Telemetry Engine
- **Purpose:** Correlates real-world usage signals to prevent premature access revocation.
- **Core Principle:** *"Absence of activity logs is NOT evidence of non-use."*
- **Mechanism:**
  - Maintains `activity_events` recording timestamp, action (`ssh_login`, `interactive_logon`, `git_push`), outcome (`Success`, `Failure`), and client IP.
  - Evaluates log coverage: if a system lacks event collection, AccessGuard explicitly states `Evidence Gap: Unverified` rather than claiming inactivity.
- **Endpoint:** `GET /api/activity`

### 2.10. Offboarding Governance Center
- **Purpose:** Prevents **"Ghost Access"** when employees resign or are terminated.
- **Mechanism:**
  - Queries `identities` with `status == 'Departed'` that still possess `access_grants` with `status == 'Active'`.
  - Highlights days since departure and severity of remaining entitlements.
  - Provides a **"Batch Offboarding Review"** action to queue all departed employee permissions for immediate certification and simulated revocation.
- **Endpoint:** `GET /api/offboarding`

### 2.11. Risk Alerts & Security Notifications Feed
- **Purpose:** Delivers an active security feed for IAM operations.
- **Alert Types:**
  - `CRITICAL_OFFBOARDING_VIOLATION`: Terminated user retains domain admin or cloud infrastructure access.
  - `ORPHAN_ADMIN_ACCOUNT`: Elevated administrative account with no verified owner identity.
  - `TOXIC_SOD_COMBINATION`: User possesses incompatible entitlements (e.g., Code Developer + Production Deployment Approver).
  - `EXCESSIVE_INACTIVITY`: Privileged account with over 90 days of confirmed inactivity.
- **Endpoint:** `GET /api/alerts`

### 2.12. Subsystem Integrations Hub
- **Purpose:** Centralized console for monitoring external dependencies and connectors.
- **Monitored Services:**
  - **Dialog Syslog Ingestion (`accesslog-main`):** Status, port `5514` binding, event ingestion count.
  - **Dialog Final ML Engine (`ml/`):** Status, model version (`Aegis V8`), trained artifact availability (`windows.joblib`, `linux.joblib`, `github.joblib`).
  - **Pasindu's Sentinel API:** Token validation, remote cloud streaming status.
  - **FTP Spool Synchronizer:** Health of incoming log directory, fallback to local sample imports.
- **Endpoints:** `GET /api/integrations`, `GET /api/connectors/runs`, `POST /api/connectors/ftp/sync`.

### 2.13. Immutable Audit Trail
- **Purpose:** Comprehensive compliance ledger for forensic investigation and regulatory audits (SOC 2 Type II, SOX).
- **Attributes:** `id`, `created_at` (UTC), `actor`, `action`, `entity`, `details`.
- **Logged Events:**
  - Account linking and unlinking (`ACCOUNT_LINK`, `ACCOUNT_UNLINK`).
  - Review decisions (`REVIEW_RETAIN`, `REVIEW_APPROVE`).
  - Simulated remediations (`SIMULATED_REVOKE`).
  - Connector synchronization runs (`CONNECTOR_IMPORT_COMPLETED`).
  - Database resets and re-seeding (`DATABASE_RESET`).
- **Endpoint:** `GET /api/audit`

### 2.14. Research Reports & Data Export Engine
- **Purpose:** Supports academic evaluation, reproducibility, and enterprise CSV/JSON reporting.
- **Export Capabilities:**
  - Full Identity & Entitlement inventory export.
  - Model ROC-AUC, Precision@K, and Reviewer time reduction metrics.
  - Connector run execution history and ingestion statistics.
- **Endpoints:** `GET /api/reports/summary`, `GET /api/metrics`.
