# Enterprise Lab — Virtual Enterprise Simulator

Standalone synthetic enterprise sandbox. No external cloud accounts, host commands, AI, ML, or access reviews. This is a new implementation, not a patch to an existing repository.

## Deploy
Install Docker with Compose, then from this directory:

```bash
docker compose up --build -d
```

Open http://localhost:8080. API documentation: http://localhost:8080/api/health (health endpoint); interactive OpenAPI documentation is available on the backend directly in local development at http://localhost:8000/docs. The compose port is loopback-only intentionally: the application has no authentication and is suitable only for a trusted local lab. Do not expose it publicly without authentication and authorization.

Create a company → choose employee size and platforms → open Simulation Controls → Start. Use the activity logs and platform consoles to inspect state and change access. SQLite data persists in the `simulator-data` Docker volume. `docker compose down` preserves data; `docker compose down -v` deletes it.

## Local development

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Tests: `cd backend && python -m unittest -v test_simulator` (install `httpx` for tests).

## API
All paths below begin `/api/companies/{company_id}` unless otherwise specified.

- GET/POST `/api/companies`: company inventory and creation
- GET `/summary`, `/departments`
- GET `/employees`, `/accounts`, `/resources`, `/grants`, `/events`: paginated collections (`offset`, `limit`, `q`; applicable collections accept `platform`; events accept `after`)
- GET `/employees/{id}`: profile, accounts, grants
- POST `/employees`, PUT `/employees/{id}`: hire, edit, promote or transfer
- POST `/employees/{id}/operation`: `terminate` or `activate`; `incomplete:true` preserves access during termination
- PUT `/employees/{id}/access`: platform, permission, status
- POST `/resources`: platform, kind, name, optional metadata/state
- POST `/resources/{id}/operation`: start, stop, rename, delete
- PUT `/grants`: employee ID, resource ID, permission (read/write/admin/remove)
- PUT `/settings`: speed, eps, active_pct, exception_pct
- POST `/simulation/{action}`: start/pause/resume/stop/reset
- GET `/stream/events?after=0`: server-sent event stream; reconnect using last received ID as `after`
- GET `/export/json` or `/export/csv`: full log export

## Model and limitations
SQLite WAL with scoped queries, indexes and a single background simulation loop. Employees share identities across the four platforms, and the engine uses account status and explicit resource grants. Events have synthetic source IPs and platform-shaped raw JSON. The initial time is 2026-01-05 UTC; schedule uses UTC hours. `eps` is attempted activities per real second; actual throughput is lower based on eligibility and schedule. Active percentage is a per-attempt probability. Recently active means activity in the last five simulated minutes, not a tracked online session. Reset clears events and last activity, resets clock and random sequence, and retains inventory. Seeded activity selection is reproducible under unchanged inventory and deterministic ticks; database IDs and concurrent user actions can affect the sequence.

This is a functional foundation, not a full fidelity clone of AWS IAM, Active Directory, GitHub or Linux. Platform-specific resources are generic typed inventory objects; membership, policies, branches, commits, PRs, sessions, file metadata and access keys are not full native state machines. Some generated activity names are illustrative and may not match the selected resource kind; Windows event ID 0 denotes unmapped simulator operations. No actual credentials are created. Department list derives from employees. The frontend uses Tailwind and custom components rather than installed shadcn/ui. No production authentication, distributed scheduling, event retention or performance certification is included. The 100,000 employee preset is supported by the data model but not a production-scale throughput guarantee. Frontend and Docker build must be verified on a machine with dependency registry access and Docker installed.
