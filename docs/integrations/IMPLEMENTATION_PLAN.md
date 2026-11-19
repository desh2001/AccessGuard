# Enterprise Simulator Integration Implementation Plan

**Objective**: Step-by-step technical roadmap to build, test, and activate the Enterprise Simulator connector in AccessGuard without interrupting real services.

---

## Phase 1: Environment & Configuration Preparation
1. **Define Environment Variables**:
   Add the following variables to `.env` and `docker-compose.yml`:
   ```bash
   SIMULATOR_ENABLED=true
   SIMULATOR_BASE_URL=http://localhost:8080
   SIMULATOR_COMPANY_ID=comp-7890
   SIMULATOR_AUTH_TOKEN=
   SIMULATOR_SYNC_INTERVAL_SECONDS=1800
   ```
2. **Seed Virtual Systems**:
   Ensure seed initialization registers the virtual simulator systems in the `systems` table:
   - `simulator-github` (Type: SaaS, Category: Code Repository)
   - `simulator-aws` (Type: Cloud, Category: Infrastructure)
   - `simulator-windows` (Type: Directory, Category: Active Directory)
   - `simulator-linux` (Type: Server, Category: OS Infrastructure)

---

## Phase 2: Connector Core Implementation (`backend/connectors/simulator_connector.py`)
1. **Create `SimulatorConnector` Class**:
   - `test_connection()`: Checks `GET /api/companies`.
   - `sync_all(company_id)`: Orchestrates batch ingestion for employees, accounts, resources, and grants.
   - `sync_employees(company_id)`: Fetches paginated employees, applies normalization, upserts `Identity`.
   - `sync_accounts(company_id)`: Fetches accounts, links to `Identity`, upserts `Account`.
   - `sync_grants(company_id)`: Fetches permissions/grants, computes cross-department metrics, upserts `AccessGrant`.
2. **Track Connector Executions**:
   - Record run telemetry in `ConnectorRun` (`records_imported`, `records_failed`, `status`).

---

## Phase 3: Real-Time Event Stream Consumer (`accessguard-accesslog` / `backend`)
1. **Build SSE Ingestion Daemon**:
   - Implements persistent HTTP streaming using `httpx` or `aiohttp` to `GET /api/companies/{company_id}/stream/events`.
   - Ingests events, parses payload, deduplicates via Redis/in-memory LRU window.
   - Persists raw logs to `ActivityEvent` with `source='EnterpriseSimulator'`.
2. **ML Trigger Hook**:
   - Dispatches platform-specific anomaly inference queries to `Dialog-Project-Final-ML` (`ml-service:8001`).
   - Flags anomalies as high-risk items in AccessGuard's risk review queue.

---

## Phase 4: Bidirectional Simulated Remediation
1. **Extend FastAPI Remediation Endpoint**:
   - In `backend/main.py`, update `POST /api/reviews/{review_id}/action` or add `POST /api/integrations/simulator/remediate`.
   - Detects if `account.source == 'EnterpriseSimulator'`.
   - Dispatches synthetic remediation payload to `POST /api/companies/{company_id}/remediate`.
   - Records an immutable record in `AuditLog` preserving the simulation audit trail.

---

## Phase 5: Frontend UI & Verification
1. **Integrations Tab Update (`frontend/src/pages/Integrations.jsx`)**:
   - Add "Enterprise Simulator" integration card showing:
     - Status: Online / Offline
     - Target Company ID & Base URL
     - Ingestion Rate (events/sec)
     - Last Sync timestamp
     - Buttons: "Sync Inventory Now", "Test Connection", "Toggle Stream".
2. **Testing & Verification**:
   - Unit tests for data transformation (`tests/test_simulator_mapping.py`).
   - Integration tests simulating SSE streams with mock server (`tests/mock_simulator_server.py`).
   - End-to-end verification verifying that simulated actions do not impact real systems.
