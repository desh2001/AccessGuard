# AccessGuard — Intelligent Identity & User Access Governance Lab

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/Frontend-React_19-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![Tailwind CSS](https://img.shields.io/badge/Styles-Tailwind_CSS_v4-38B2AC?style=flat-square&logo=tailwind-css)](https://tailwindcss.com)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_17-336791?style=flat-square&logo=postgresql)](https://www.postgresql.org)
[![Docker Compose](https://img.shields.io/badge/Orchestration-Docker_Compose-2496ED?style=flat-square&logo=docker)](https://docs.docker.com/compose/)
[![Scikit-Learn](https://img.shields.io/badge/ML-Isolation_Forest-F7931E?style=flat-square&logo=scikit-learn)](https://scikit-learn.org)
[![License](https://img.shields.io/badge/License-Research_Demo-blue.svg?style=flat-square)](#important-research-notice)

**AccessGuard** is a comprehensive, local-first research and demonstration platform for **AI-assisted Identity Governance and Administration (IGA)**. It unifies canonical identity correlation, cross-system technical account mapping, entitlement risk heuristics, sampled activity verification, and unsupervised machine learning anomaly detection into an intuitive enterprise-grade dashboard.

The platform demonstrates how organizations can tackle **"Access Creep"**, orphaned accounts, dormant privileges, and toxic entitlement combinations while enforcing **human-in-the-loop** decision making and non-destructive simulated remediation.

---

> ### ⚠️ IMPORTANT RESEARCH NOTICE
> **THIS IS A RESEARCH AND DEMONSTRATION PROTOTYPE, NOT A PRODUCTION IDENTITY PLATFORM.**
> - **Default Synthetic Data:** The lab seeds synthetic identities, systems, accounts, and activities by default.
> - **Localhost Binding Only:** The backend and frontend are configured for local loopback (`127.0.0.1`) only. Do NOT expose this platform directly to the public internet.
> - **Simulated Remediation:** For safety and audit compliance, access revocations are strictly **simulated in the local database**. No remote commands or destructive API calls are ever sent to live Active Directory, Linux hosts, or cloud providers.
> - **Human-in-the-Loop:** ML anomaly scores are **advisory percentiles** designed to prioritize human review queues—they never automatically revoke or certify permissions.

---

## Table of Contents

- [Ecosystem Architecture](#ecosystem-architecture)
- [Repository Structure](#repository-structure)
- [Module Status & Capabilities](#module-status--capabilities)
- [Prerequisites](#prerequisites)
- [Quick Setup](#quick-setup)
  - [Automated Windows Setup (One-Click)](#1-automated-windows-setup-powershell)
  - [Manual Setup (Step-by-Step)](#2-manual-step-by-step-setup)
- [Dialog Ecosystem Integration](#dialog-ecosystem-integration)
  - [1. Dialog Access Log (Syslog Collector)](#1-dialog-access-log-syslog-collector)
  - [2. Dialog Final ML Microservice](#2-dialog-final-ml-microservice)
- [End-to-End Workflow Walkthrough](#end-to-end-workflow-walkthrough)
- [Connectors & Data Ingestion](#connectors--data-ingestion)
- [Environment Configuration](#environment-configuration)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [Research Methodology & Guardrails](#research-methodology--guardrails)
- [Documentation Links](#documentation-links)

---

## Ecosystem Architecture

The AccessGuard research suite integrates three specialized subsystems into a unified governance workflow:

```text
                                 ┌──────────────────────────────────────────────────┐
                                 │               Client Web Browser                 │
                                 │         http://127.0.0.1:5173 (React UI)         │
                                 └────────────────────────┬─────────────────────────┘
                                                          │ HTTP / Vite Proxy
                                                          ▼
┌─────────────────────────────────┐              ┌──────────────────────────────────┐
│  accesslog-main (Pasindu)       │              │  AccessGuard Core Backend        │
│  - TCP Syslog Ingestion (:5514) │ FTP Sync /   │  - FastAPI REST API (:8000)      │
│  - Device & Event Explorer      ├─────────────►│  - Identity & Account Mapping    │
│  - Log Normalization            │ Local Spool  │  - Risk Heuristics Engine        │
└─────────────────────────────────┘              │  - Access Review Campaign Mgr    │
                                                 └────────┬──────────────────┬──────┘
                                                          │                  │
                         SQLAlchemy / Alembic (Port 5434) │                  │ HTTP POST /predict-risk
                                                          ▼                  ▼ (Port 8001)
                                                 ┌─────────────────┐ ┌──────────────────────────────┐
                                                 │ PostgreSQL 17   │ │ Dialog Final ML (Hashan)     │
                                                 │ (Docker Compose)│ │ - Multi-Platform Isolation   │
                                                 │                 │ │   Forest (Win, Linux, GitHub)│
                                                 │ accessguard_lab │ │ - Peer Ratio Anomaly Engine  │
                                                 └─────────────────┘ └──────────────────────────────┘
```

### Subsystem Overview

1. **AccessGuard Core (`backend/` & `frontend/`):**
   - **Backend:** FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (running on published Windows port `5434`). Manages canonical identities, mapped accounts, entitlement risk scoring, review campaigns, simulated revocations, and audit trails.
   - **Frontend:** React 19, Tailwind CSS v4, Lucide Icons, and Recharts. A dark-themed security operations dashboard featuring 12 interactive governance views.
2. **Dialog Access Log (`accesslog-main/`):**
   - Syslog collector receiving TCP log events on port `5514`, normalizing authentication logs, observing active devices, and exposing logs via an API and FTP spool integration.
3. **Dialog Final ML Engine (`ml/` & `backend/mock_ml_service.py`):**
   - Advanced multi-platform quarterly Isolation Forest model (Windows AD, Linux PAM, GitHub OAuth) scoring entitlement anomalies against peer groups. Connects to AccessGuard via HTTP REST (`/predict-risk`). Includes fallback to local in-process Scikit-Learn if offline.

---

## Repository Structure

```text
AccessGuard/
├── backend/                        # AccessGuard Core FastAPI backend
│   ├── alembic/                    # Database migration versions
│   ├── connectors/                 # CSV, GitHub REST, and FTP connectors
│   ├── sample_imports/             # Sample CSVs (Linux, Windows) and FTP spool logs
│   ├── tests/                      # PyTest automated unit test suite
│   ├── activity.py                 # Activity log heuristics & flag processing
│   ├── ai_engine.py                # Local Isolation Forest anomaly scoring fallback
│   ├── check_db.py                 # Database connectivity verification utility
│   ├── database.py                 # SQLAlchemy session management & engine
│   ├── main.py                     # FastAPI application router & API endpoints
│   ├── ml_client.py                # HTTP client adapter for Dialog Final ML microservice
│   ├── mock_ml_service.py          # Standalone simulation of external ML microservice
│   ├── models.py                   # Relational ORM models (Identity, Account, Review, etc.)
│   ├── requirements.txt            # Python dependencies (FastAPI, Scikit-learn, etc.)
│   ├── risk.py                     # Rule-based access risk scoring algorithms
│   └── seed_demo.py                # Idempotent demo dataset seeder
├── frontend/                       # AccessGuard Core React 19 Dashboard
│   ├── src/
│   │   ├── App.jsx                 # Main application containing all 12 governance tabs
│   │   ├── main.jsx                # React DOM entry point
│   │   └── styles.css              # Tailwind CSS styles and custom utility classes
│   ├── package.json                # Node dependencies (React 19, Recharts, Lucide, Tailwind)
│   └── vite.config.js              # Vite configuration with /api reverse proxy to :8000
├── ml/                             # Dialog Final ML Service (Aegis V8 Multi-Platform)
│   ├── backend/                    # ML microservice backend & quarterly training pipelines
│   ├── frontend/                   # ML specific inspection UI (React / TypeScript)
│   ├── sample-data/                # Synthetic enterprise access & training datasets
│   └── docker-compose.yml          # Container configuration for standalone ML stack
├── accesslog-main/                 # Dialog Access Log Ingestion Service
│   ├── api/                        # FastAPI log explorer API
│   ├── collector/                  # TCP Syslog listener daemon (port 5514)
│   ├── frontend/                   # Syslog live event viewer
│   └── docker-compose.yml          # Stack orchestration for collector and database
├── scripts/                        # Automation & startup scripts for Windows PowerShell
│   ├── setup-windows.ps1           # Full automated installer (Docker, venv, DB, seed, npm)
│   ├── start-backend.ps1           # Launch script for backend API (:8000)
│   └── start-frontend.ps1          # Launch script for frontend UI (:5173)
├── docs/                           # Extended research documentation
│   ├── RESEARCH_METHODOLOGY.md     # Academic methodology, validation, and metrics
│   └── SINHALA_GUIDE.md            # Sinhala language operations guide
├── .gitignore                      # Complete repository ignore rules
├── docker-compose.yml              # Core PostgreSQL database container (port 5434:5432)
└── README.md                       # Master project documentation
```

---

## Module Status & Capabilities

| Module | Operational Status | Description |
|---|---|---|
| **Overview Dashboard** | Active | High-level metrics, system inventory, risk distribution, and review campaign progress. |
| **Identity Directory** | Active | Canonical employee directory linking identities across HR, IT, and external platforms. |
| **Account Mapping** | Active | Correlates technical usernames to employees; highlights unlinked/orphaned service accounts. |
| **Access Inventory** | Active | Comprehensive entitlement catalog with permission scopes and fine-grained resource tags. |
| **AI Risk Analysis** | Active | Hybrid scoring comparing explainable policy rules against ML Isolation Forest percentiles. |
| **Access Reviews** | Active | Generates campaign reviews; supports **Retain** and **Approve Removal** reviewer actions. |
| **Simulated Remediation**| Active | Updates local database states to simulate revocation without touching remote servers. |
| **Activity Evidence** | Active | Correlates authentication events, failed logins, and UTC time stamps with account usage. |
| **Offboarding Center** | Active | Identifies departed employees who still retain active access across corporate systems. |
| **Integrations** | Active | Monitors FTP sync with `accesslog-main` and live connection to `Dialog Final ML`. |
| **Audit Trail** | Active | Chronological record of administrative decisions, linkages, and simulated revocations. |
| **Research Reports** | Active | Analytical reports and connector provenance data exportable to CSV/JSON. |

---

## Prerequisites

Before starting, ensure you have the following installed on your machine:

1. **Docker Desktop** (configured with Linux containers enabled).
2. **Python 3.11+** (available on PATH via `python` or `py`).
3. **Node.js LTS** (version 18.x or 20.x+) and `npm`.
4. **Git** (for version control).

---

## Quick Setup

### 1. Automated Windows Setup (PowerShell)

An automated script is provided in `scripts/setup-windows.ps1` that spins up PostgreSQL, sets up the Python virtual environment, runs database migrations, seeds demo data, executes unit tests, and installs frontend dependencies.

Open PowerShell in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

Once the setup completes, open two separate PowerShell windows to start the services:

* **Terminal 1 (Backend):**
  ```powershell
  .\scripts\start-backend.ps1
  ```
* **Terminal 2 (Frontend):**
  ```powershell
  .\scripts\start-frontend.ps1
  ```

---

### 2. Manual Step-by-Step Setup

If you prefer to configure each component manually or are running on Linux/macOS:

#### Step 1: Start PostgreSQL via Docker Compose
The repository includes a dedicated `docker-compose.yml` for PostgreSQL. To prevent conflicts with any local PostgreSQL instance listening on default port `5432`, the container maps host port **`5434`** to container port **`5432`**.

From the repository root:
```bash
docker compose up -d
docker compose ps
```
Verify that `accessguard-complete-postgres` is running and healthy on port `127.0.0.1:5434->5432/tcp`.

#### Step 2: Configure & Start AccessGuard Backend
```bash
cd backend

# Create your .env file from the provided template
# (On Windows PowerShell: Copy-Item .env.example .env)
cp .env.example .env

# Create and activate Python virtual environment
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify database connection
python check_db.py

# Run Alembic database migrations
python -m alembic upgrade head

# Seed idempotent demo data
python seed_demo.py

# Launch FastAPI development server
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

#### Step 3: Configure & Start AccessGuard Frontend
Open a new terminal:
```bash
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

#### Step 4: Access the Dashboard & API
- **Web UI:** [http://127.0.0.1:5173](http://127.0.0.1:5173)
- **Interactive Swagger Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **API Health Check:** [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## Dialog Ecosystem Integration

AccessGuard integrates seamlessly with the two partner repositories:

```text
[Dialog Access Log] ──(FTP/SFTP or Spool)──► [AccessGuard FTP Ingestion] ──► [PostgreSQL]
                                                                                   │
[Dialog Final ML]  ◄──────(HTTP POST /predict-risk)────────────────────────────────┘
```

### 1. Dialog Access Log (Syslog Collector)
- **Repo Directory:** `accesslog-main/`
- **Purpose:** Ingests raw syslog messages over TCP port `5514` into PostgreSQL, identifies communicating devices, and prepares audit logs.
- **Syncing with AccessGuard:**
  1. Configure FTP parameters in `backend/.env` (defaults to local spool).
  2. In the AccessGuard dashboard, navigate to **Integrations** -> click **"Sync Dialog FTP Logs"**.
  3. If no live FTP server is running, AccessGuard automatically ingests fallback events from `backend/sample_imports/ftp_spool/` to ensure offline resilience.

### 2. Dialog Final ML Microservice
- **Repo Directory:** `ml/` (and simulated via `backend/mock_ml_service.py`)
- **Purpose:** Computes multi-platform anomaly scores across Windows, Linux, and GitHub accounts using an Isolation Forest model with peer-group comparison.
- **Running the Service Locally:**
  In a new terminal:
  ```powershell
  cd backend
  .\.venv\Scripts\python.exe -m uvicorn mock_ml_service:app --port 8001 --host 127.0.0.1
  ```
- **Verification:**
  1. In AccessGuard UI, go to **Integrations** -> click **"Ping ML Service"**.
  2. The badge in **AI Risk Analysis** will transition to **"Dialog Final ML (Live)"**.
  3. If offline, AccessGuard gracefully falls back to its built-in in-process Scikit-Learn Isolation Forest engine.

---

## End-to-End Workflow Walkthrough

Experience the primary access governance workflow within the web dashboard:

1. **Overview Dashboard:** Examine organization risk metrics, entitlement distribution, and review campaign status.
2. **Account Mapping:** Identify unlinked technical accounts (e.g., `svc-backup`, `dba_admin`). Link an unlinked account to an employee identity and observe the audit trail creation.
3. **Activity Evidence:** Review sampled authentication timestamps and failed attempt flags. Understand why absence of logs does not necessarily equal absence of access.
4. **AI Risk Analysis:** Compare transparent rule-based risk scores with unsupervised Isolation Forest anomaly percentiles. Review why certain entitlements trigger high-risk alerts.
5. **Access Reviews:**
   - Click **"Generate risk-based reviews"** to generate review tickets for elevated risks.
   - For each ticket, choose to **Retain** or **Approve removal**.
   - If removal is approved, execute **"Simulate revoke"** to verify that the grant status changes to `Revoked (Simulated)` locally.
6. **Offboarding Center:** View departing or terminated employees who still retain active account entitlements. Initiate offboarding review batches.
7. **Audit & Research Reports:** Inspect the immutable audit log and export research metrics via CSV or JSON.

---

## Connectors & Data Ingestion

AccessGuard supports external data imports via safe, controlled CLI tools:

### CSV Entitlement Import
Import accounts and entitlements from operator-supplied CSV files:
```powershell
cd backend
.\.venv\Scripts\python.exe -m connectors.csv_import --file sample_imports\linux_accounts.csv --system LIN
.\.venv\Scripts\python.exe -m connectors.csv_import --file sample_imports\windows_accounts.csv --system WIN
```
*Required CSV columns:* `external_account_id,username,permission,resource` (optional: `account_email`).

### Read-Only GitHub Connector
Inspect repository collaborators and team memberships using a read-only Personal Access Token (PAT):
```powershell
cd backend
# Requires GITHUB_READ_TOKEN and GITHUB_ORG configured in backend/.env
.\.venv\Scripts\python.exe -m connectors.github_readonly --org YOUR_TEST_ORG --max-repos 10
```
*Security Note: The GitHub connector uses REST GET requests only and performs zero mutation or write operations.*

---

## Environment Configuration

### `backend/.env`
```env
# Local Lab Database (PostgreSQL container published on Windows port 5434)
DATABASE_URL=postgresql+psycopg://accessguard_lab:research-local-only@127.0.0.1:5434/accessguard_lab

# Dialog Access Log - FTP Configuration
FTP_HOST=127.0.0.1
FTP_PORT=21
FTP_USER=dialog_access
FTP_PASS=dialog_secure_pass
FTP_DIR=/incoming_logs

# Dialog Final ML Service Configuration
ML_SERVICE_URL=http://127.0.0.1:8001

# Optional Read-Only GitHub Organization Import
# GITHUB_READ_TOKEN=github_pat_...
# GITHUB_ORG=your-test-organization
```

### `ml/.env` (For Standalone ML Stack)
```env
POSTGRES_PASSWORD=your_secure_password
JWT_SECRET=your_32_character_secret_key
DEMO_ADMIN_PASSWORD=admin_password
DEMO_REVIEWER_PASSWORD=reviewer_password
```

### `accesslog-main/.env` (For Syslog Stack)
```env
POSTGRES_PASSWORD=your_secure_password
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_admin_password
JWT_SECRET=your_jwt_secret
SYSLOG_BIND_IP=127.0.0.1
```

---

## Testing & Quality Assurance

Run the automated backend test suite using PyTest:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite validates:
- Schema migrations and ORM constraints
- Risk scoring heuristic rules
- Isolation Forest anomaly percentile computation
- Review campaign generation and state transitions
- CSV and mocked connector ingestion boundaries

---

## Troubleshooting & FAQ

#### 1. `FATAL: password authentication failed for user "accessguard_lab"`
- **Cause:** A previous PostgreSQL container or volume from an earlier build exists on port 5434 with different credentials.
- **Fix:** Verify `backend/.env` credentials. If restarting cleanly, stop the container with `docker compose down` (do NOT delete data unless you intend to reset the lab).

#### 2. `Port 5434 is already allocated`
- **Cause:** Another container or process is bound to `5434`.
- **Fix:** Check running containers with `docker ps`. Stop any conflicting containers:
  ```powershell
  docker stop accessguard-phase2-postgres
  ```

#### 3. Frontend displays "Failed to fetch" or blank tables
- **Cause:** Backend API is not running on port 8000 or Vite reverse proxy is blocked.
- **Fix:** Ensure FastAPI is active (`http://127.0.0.1:8000/api/health` returns `{"status":"ok"}`).

#### 4. `ModuleNotFoundError` when running Python scripts
- **Cause:** Python virtual environment is either not activated or missing packages.
- **Fix:** Ensure you are using the virtual environment's Python: `.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`.

---

## Research Methodology & Guardrails

AccessGuard was developed under strict research governance principles:

1. **Explainable AI (XAI):** Machine learning models provide **advisory anomaly percentiles**, accompanied by explicit human-readable reasons (e.g., cross-department grant, high privilege, inactive interval).
2. **Zero Automated Revocation:** The system never executes automatic unverified permission removals. Remediation requires an authorized reviewer's explicit confirmation and is executed purely as a local simulation.
3. **Absence of Evidence is Not Evidence of Absence:** Missing activity logs are transparently flagged as *unverified activity* rather than conclusively labeled as dormant access.
4. **Data Privacy:** All employee names, email addresses, and server identifiers in demo seeds are synthetically generated.

For comprehensive details on scoring formulas and validation metrics, consult [docs/RESEARCH_METHODOLOGY.md](docs/RESEARCH_METHODOLOGY.md).

---

## Documentation Links

- [Research Methodology & Metrics](docs/RESEARCH_METHODOLOGY.md)
- [Sinhala Operations Guide (සිංහල මාර්ගෝපදේශය)](docs/SINHALA_GUIDE.md)
- [Dialog Final ML Guide](ml/V8_THREE_PLATFORM_MODELS_GUIDE.md)
- [Syslog Ingestion Notes](accesslog-main/README.md)
