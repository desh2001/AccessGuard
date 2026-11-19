# Enterprise Simulator Integration Specification
**System**: AccessGuard Identity Governance & Administration (IGA)  
**Target Integration**: Enterprise Simulator (`http://localhost:8080`)  
**Document Version**: 1.0.0  
**Classification**: System Architecture & Engineering Specification  

---

## 1. Executive Summary & Purpose

Enterprise Simulator is an external standalone application designed to simulate large corporate infrastructures (100 to 100,000 employees) across four primary enterprise platforms:
1. **GitHub Enterprise** (Organizations, Repositories, Teams, Permissions, Audit logs)
2. **AWS Cloud** (IAM Roles, Policies, S3/EC2/RDS resources, CloudTrail logs)
3. **Windows & Active Directory** (Domains, OUs, Security Groups, Windows Event Logs / Event ID 4624, 4625, 4672)
4. **Linux Enterprise** (PAM/SSHD auth, Sudoers privileges, Syslog `/var/log/auth.log`)

The simulator generates synthetic entities (employees, accounts, grants, resources) and continuous log activity streams. It performs **no AI/ML, risk detection, or governance**. 

**AccessGuard** owns:
- Ingestion of identity and access governance state.
- Live log stream collection and normalization.
- Unsupervised Isolation Forest anomaly detection across platforms (Aegis V8 models).
- Rule-based access reviews, privilege creep detection, and segregation-of-duties (SoD) enforcement.
- Automated and human-reviewed simulated remediation (closing the loop without affecting real production assets).

This document establishes the formal, production-grade integration specification between AccessGuard and Enterprise Simulator without modifying or destabilizing existing real connectors.

---

## 2. Existing AccessGuard Architecture Analysis

A rigorous inspection of the current AccessGuard codebase reveals the following baseline architecture:

### 2.1 Microservices & Core Services
- **Backend API (`backend/main.py`)**: FastAPI application on port `8000`. Exposes CRUD and analytical endpoints for identities, accounts, access grants, reviews, audit logs, and integrations.
- **AccessLog Service (`accesslog-service`)**: Microservice on port `8002` (and TCP port `5514` for Syslog ingestion) located at `accessguard-accesslog/`. Provides log ingestion from Sentinel VPS (`https://host.pasinduudana.me`) and local network Syslog streams.
- **ML Service (`ml-service`)**: Microservice on port `8001` (`ml/main.py` / `Dialog-Project-Final-ML v1.4`). Houses three platform-specific Isolation Forest models:
  - Windows AD model (160 trees)
  - Linux Host model (160 trees)
  - GitHub OAuth model (160 trees)
- **PostgreSQL Database (`postgres`)**: Port `5434:5432` (Docker internal: 5432). Database name: `accessguard`.
- **Frontend Dashboard (`frontend/`)**: React 18 + Vite + Tailwind CSS dashboard running on port `5173`.

### 2.2 Existing Database Models (`backend/models.py`)
- `Identity`: Represents employees/contractors (`id`, `name`, `email`, `department`, `job_title`, `manager`, `type`, `status`).
- `System`: Connected systems (`id`, `name`, `type`, `category`, `description`, `last_sync`).
- `Account`: Platform accounts (`id`, `identity_id`, `system_id`, `external_account_id`, `username`, `email`, `status`, `source`).
- `AccessGrant`: Entitlements/permissions (`id`, `account_id`, `permission`, `resource`, `privilege`, `cross_department`, `status`, `source`).
- `ActivityEvent`: Log events (`id`, `account_id`, `occurred_at`, `action`, `outcome`, `ip_address`, `source`, `raw_message`).
- `Review`: Governance access review records (`id`, `grant_id`, `reviewer`, `status`, `decision`, `reason`, `reviewed_at`).
- `AuditLog`: Action tracking for remediation and administrative decisions (`id`, `actor`, `action`, `target_type`, `target_id`, `details`, `timestamp`).
- `ConnectorRun`: Sync job tracking (`id`, `source`, `started_at`, `finished_at`, `status`, `records_imported`, `records_failed`, `details`).

---

## 3. Integration Architecture & Strategy

To achieve high throughput, complete coverage, and real-time anomaly detection, AccessGuard will implement a **Dual-Channel Hybrid Integration Architecture**:

```
+-------------------------------------------------------------+
|                     Enterprise Simulator                    |
|                    (http://localhost:8080)                  |
+------------------------------+------------------------------+
                               |
            +------------------+------------------+
            |                                     |
   [Channel 1: REST Polling]             [Channel 2: Live SSE]
   Inventory Sync (Every 10-60m)         Realtime Events
            |                                     |
            v                                     v
+------------------------------+     +------------------------------+
| Simulator Inventory Syncer   |     | Simulator SSE Event Listener |
| (backend/connectors/)        |     | (accesslog-service / backend)|
+--------------+---------------+     +--------------+---------------+
               |                                    |
               +-----------------+------------------+
                                 |
                                 v
              +------------------------------------+
              |      AccessGuard Data Store        |
              |       (PostgreSQL Database)        |
              +-----------------+------------------+
                                |
             Feature Extraction | Normalization
                                v
              +------------------------------------+
              |      Dialog ML Microservice        |
              |     Isolation Forest Inference     |
              +-----------------+------------------+
                                |
                                v
              +------------------------------------+
              |      AccessGuard Dashboard         |
              |   (Live Reviews & Remediation)     |
              +-----------------+------------------+
                                |
             Simulated Remediation API Call
                                v
+-------------------------------------------------------------+
|         Simulator Action Webhook / Remediation API          |
|          POST /api/companies/{company_id}/remediate         |
+-------------------------------------------------------------+
```

### 3.1 Inventory Synchronization (Channel 1: REST Polling)
- **Type**: Scheduled periodic pull + on-demand "Sync Now" button.
- **Scope**: Companies, Employees, Accounts, Resources, Grants.
- **Frequency**: Configurable (e.g., every 30 minutes, or triggered via UI).
- **Mechanism**: Dedicated connector `SimulatorConnector` (`backend/connectors/simulator_connector.py`) orchestrating pagination (`limit`, `offset`), tracking last-sync via `ConnectorRun`.

### 3.2 Continuous Activity Ingestion (Channel 2: Server-Sent Events - SSE)
- **Type**: Persistent HTTP streaming connection.
- **Endpoint**: `GET /api/companies/{company_id}/stream/events`.
- **Mechanism**: An async background worker in `accesslog-service` (or `backend/services/simulator_listener.py`) maintains an active SSE stream connection with exponential backoff and reconnect logic.
- **Event Deduplication**: Windowed hash buffer based on `(event_id, occurred_at, account_id, action)`.

---

## 4. Entity & Data Mapping

All imported objects are strictly tagged with:
- `source = 'EnterpriseSimulator'`
- `system_id = 'simulator-{platform}'` (e.g., `simulator-github`, `simulator-aws`, `simulator-windows`, `simulator-linux`).

### 4.1 Company -> System / Organization Scope
| Simulator Source Field | AccessGuard Destination | Data Type | Transform / Rule |
| :--- | :--- | :--- | :--- |
| `company.id` | `System.category` / Meta | String | Stored as `company_id` tag in connector metadata |
| `company.name` | `System.name` prefix | String | Display name prefix e.g., "Simulator [Acme Corp]" |
| `company.created_at` | `ConnectorRun.details` | Timestamp | Recorded in run logs |

### 4.2 Employee -> Identity
| Simulator Source Field | AccessGuard Destination (`Identity`) | Data Type | Transform / Rule |
| :--- | :--- | :--- | :--- |
| `employee.id` | `Identity.id` | String | Prefixed: `sim-emp-{id}` to guarantee no collisions |
| `employee.first_name` + `last_name`| `Identity.name` | String | Concat trimmed |
| `employee.work_email` | `Identity.email` | String | Normalized lowercase; unique key |
| `employee.department` | `Identity.department` | String | Direct map (e.g., "Engineering", "Finance") |
| `employee.job_title` | `Identity.job_title` | String | Direct map |
| `employee.manager_email` | `Identity.manager` | String | Email reference |
| `employee.status` | `Identity.status` | String | Map: `active`->`Active`, `terminated`->`Departed`, `on_leave`->`Suspended` |
| Literal `'Human'` | `Identity.type` | String | Set to `'Human'` (or `'Service'` for service accs) |

### 4.3 Account -> Account
| Simulator Source Field | AccessGuard Destination (`Account`) | Data Type | Transform / Rule |
| :--- | :--- | :--- | :--- |
| `account.id` | `Account.id` | String | Prefixed: `sim-acc-{id}` |
| `account.employee_id` | `Account.identity_id` | String | Foreign key to `Identity.id` |
| `account.platform` | `Account.system_id` | String | Mapped to `sim-github`, `sim-aws`, `sim-win`, `sim-linux` |
| `account.account_name` | `Account.username` | String | Platform login / username |
| `account.email` | `Account.email` | String | Email |
| `account.is_active` | `Account.status` | String | `true` -> `Active`, `false` -> `Suspended` |
| `'EnterpriseSimulator'` | `Account.source` | String | Stored explicitly as `'EnterpriseSimulator'` |

### 4.4 Grants & Permissions -> AccessGrant
| Simulator Source Field | AccessGuard Destination (`AccessGrant`) | Data Type | Transform / Rule |
| :--- | :--- | :--- | :--- |
| `grant.id` | `AccessGrant.id` | String | Prefixed: `sim-grt-{id}` |
| `grant.account_id` | `AccessGrant.account_id` | String | FK to `Account.id` |
| `grant.permission_name` | `AccessGrant.permission` | String | e.g., `admin`, `s3:PutObject`, `Domain Admins`, `sudo ALL` |
| `grant.resource_name` | `AccessGrant.resource` | String | e.g., `repo:org/payments`, `arn:aws:s3:::prod-data`, `DC01`, `srv-linux-01` |
| `grant.is_privileged` | `AccessGrant.privilege` | Boolean | Direct boolean flag |
| Cross-Dept Computation | `AccessGrant.cross_department` | Boolean | True if employee dept != resource designated dept |
| `grant.status` | `AccessGrant.status` | String | Default `'Active'` |
| `'EnterpriseSimulator'` | `AccessGrant.source` | String | Stored explicitly as `'EnterpriseSimulator'` |

### 4.5 Events -> ActivityEvent
| Simulator Source Field | AccessGuard Destination (`ActivityEvent`) | Data Type | Transform / Rule |
| :--- | :--- | :--- | :--- |
| Auto-generated | `ActivityEvent.id` | Integer / UUID | Auto-increment primary key |
| Resolved via `account_id` | `ActivityEvent.account_id` | String | FK to `Account.id` |
| `event.timestamp` | `ActivityEvent.occurred_at` | Timestamp | ISO 8601 parsed to UTC DateTime |
| `event.action` | `ActivityEvent.action` | String | e.g., `LOGIN`, `PRIVILEGE_ELEVATION`, `REPO_CLONE` |
| `event.status` / `outcome` | `ActivityEvent.outcome` | String | `SUCCESS`, `FAILURE`, `DENIED` |
| `event.source_ip` | `ActivityEvent.ip_address` | String | Valid IPv4/IPv6 address |
| `event.platform` | `ActivityEvent.source` | String | `sim-github`, `sim-aws`, `sim-windows`, `sim-linux` |
| Raw JSON string | `ActivityEvent.raw_message` | String | Full raw payload preserved as JSON string |

---

## 5. ML Engine Compatibility & Feature Pipeline

AccessGuard's ML microservice (`ml/main.py`) operates three pre-trained Isolation Forest models:
1. **Windows AD Model**: Evaluates `[failed_logins_24h, off_hours_ratio, privilege_usage_rate, unique_ips_7d, admin_account_flag]`
2. **Linux Host Model**: Evaluates `[sudo_executions_24h, ssh_failures_24h, non_standard_ports_ratio, session_duration_avg, root_escalation_flag]`
3. **GitHub Enterprise Model**: Evaluates `[after_hours_commit_ratio, sensitive_repo_access_count, personal_email_clone_count, permission_change_count]`

### 5.1 Real-Time Feature Ingestion Flow
When simulator events arrive via SSE, the AccessGuard event ingestion handler triggers the micro-batch feature aggregator:
1. Maps `event.platform` to target model:
   - `windows` -> Windows IsolationForest endpoint (`/predict/windows`)
   - `linux` -> Linux IsolationForest endpoint (`/predict/linux`)
   - `github` -> GitHub IsolationForest endpoint (`/predict/github`)
   - `aws` -> CloudTrail Anomaly Engine / Rule-based IAM evaluator
2. Aggregates rolling window statistics from the database.
3. Computes anomaly score: `anomaly_score = model.decision_function(X)`.
4. If `anomaly_score < threshold` or `prediction == -1`, automatically generate an unreviewed `Review` record with `Review.status = 'Pending'` and flag high-risk tags in the dashboard.

---

## 6. Bidirectional Simulated Remediation

Access reviews in AccessGuard allow administrators to approve or revoke entitlements and suspend compromised accounts. Because Enterprise Simulator generates synthetic resources, **AccessGuard must remediate virtual simulator state, never touching production infrastructure.**

### Remediation Action Matrix:
| Target Platform | AccessGuard Action | Simulator Remediation Endpoint | Simulated Result |
| :--- | :--- | :--- | :--- |
| **GitHub** | Revoke Repository Access | `POST /api/companies/{cid}/remediate/github/revoke` | User removed from collaborator list or team |
| **AWS** | Detach IAM Policy | `POST /api/companies/{cid}/remediate/aws/detach-policy` | Policy removed from virtual IAM role/user |
| **Windows** | Disable AD User | `POST /api/companies/{cid}/remediate/windows/disable-user` | `account_status` set to disabled in virtual AD |
| **Linux** | Revoke Sudo / Lock User | `POST /api/companies/{cid}/remediate/linux/lock-account` | Sudoers entry cleared; password locked |
| **All Platforms** | Complete Offboarding | `POST /api/companies/{cid}/remediate/offboard` | All connected virtual accounts disabled |

Every remediation call logs an entry in `AuditLog` with:
- `actor = 'AccessGuard Reviewer: <user_email>'`
- `target_type = 'SimulatedAccount' | 'SimulatedGrant'`
- `details = '{"simulated": true, "company_id": "...", "response_code": 200}'`

---

## 7. Security, Sandboxing & Workspace Isolation

1. **Virtual Namespace Isolation**: All entities created by the simulator connector are prefixed with `sim-` and marked `source='EnterpriseSimulator'`. Under no circumstances can a simulated remediation command execute real AWS CLI, GitHub API, Windows PowerShell, or SSH Linux commands.
2. **Credential Protection**: Simulator API credentials (if configured with Bearer tokens) are encrypted in the AccessGuard secrets vault or environment variables.
3. **Replay Protection**: The SSE ingestion consumer maintains an in-memory LRU cache of the last 10,000 `event_id`s to prevent duplicate log processing if the stream reconnects.
4. **Failure Recovery**: If Enterprise Simulator is temporarily unavailable (e.g., restarted on `localhost:8080`), the connector enters exponential backoff (initial delay: 2s, maximum delay: 60s) without blocking AccessGuard's core web server.
