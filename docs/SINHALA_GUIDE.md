# AccessGuard Complete — Sinhala Setup & Workflow

## ඇයි මේ project එක?

මෙය AI-assisted User Access Governance final-year research එකකට හදපු working **local lab prototype** එකක්. Enterprise production application එකක් නෙමෙයි. Database, UI, risk scores, reviews, audit වගේ modules එකට connect කරලා තියෙනවා. Real company access removal කරන්න බැහැ; ඉතාම වැදගත් safety limitation එක ඒකයි.

## ඔයාගේ Port 5434 error එක fix කරන විදිහ

ඔයා කලින් Docker එකේ `127.0.0.1:5434->5434/tcp` පෙන්වලා තිබුණා. Default PostgreSQL port එක Docker container ඇතුළේ **5432**. ඒ නිසා මේ project එකේ Compose mapping එක:

```yaml
ports:
  - '127.0.0.1:5434:5432'
```

`backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://accessguard_lab:research-local-only@127.0.0.1:5434/accessguard_lab
```

පරණ Phase 2 container එක 5434 use කරනවා නම් **පරණ volume delete නොකර** මේ command එක run කරන්න:

```powershell
docker stop accessguard-phase2-postgres
```

එතකොට මේ project එකේ වෙනම `accessguard-complete-postgres` database container එක start කරන්න පුළුවන්.

## Windows 11 PowerShell step by step

ZIP එක `C:\Users\ASUS\Downloads\accessguard-complete` කියන folder එකට extract කරලා VS Code එකෙන් open කරන්න. Docker Desktop active ද බලන්න.

**Terminal 1 — Docker**:

```powershell
cd C:\Users\ASUS\Downloads\accessguard-complete
docker compose up -d
docker compose ps
```

**Terminal 2 — Backend**:

```powershell
cd C:\Users\ASUS\Downloads\accessguard-complete\backend
Copy-Item .env.example .env
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m check_db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m seed_demo
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 3 — Frontend**:

```powershell
cd C:\Users\ASUS\Downloads\accessguard-complete\frontend
npm install
npm run dev
```

Browser: `http://127.0.0.1:5173`, API docs: `http://127.0.0.1:8000/docs`.

## Working demo එකේ full flow

1. **Identities**: Employee ලා සහ department/status බලන්න.
2. **Linked Accounts**: GitHub/Windows/Linux system accounts එක employee record එකකට manually link කරන්න. Automatic name matching කරන්නේ නැහැ.
3. **Access Inventory**: කාට මොන permission තියෙනවද බලන්න.
4. **Activity Evidence**: Sample event logs සහ unusual behavior flags බලන්න. Logs නැති එක access භාවිතා වුණේ නැහැ කියන සාක්ෂියක් නෙමෙයි.
5. **AI Risk Analysis**: Rule score එක සහ Isolation Forest anomaly percentile එක compare කරන්න. මේක statistical research demo model එකක්, confirmed maliciousness prediction එකක් නෙමෙයි.
6. **Risk Alerts**: Review කරන්න ඕන grants පෙන්නයි.
7. **Access Reviews**: **Generate risk-based reviews** → **Retain** නැත්නම් **Approve removal** → **Simulate revoke**. Real system permissions වෙනස් වෙන්නේ නැහැ.
8. **Offboarding**: Departed employee ලාගේ active permissions බලන්න.
9. **Audit Reports**: Reviewer decisions ඇතුළු events history බලන්න.
10. **Research Reports**: Counts, review progress, connector provenance export කරන්න.

## CSV import example

```powershell
cd C:\Users\ASUS\Downloads\accessguard-complete\backend
.\.venv\Scripts\python.exe -m connectors.csv_import --file sample_imports\linux_accounts.csv --system LIN
```

මේක sample CSV data PostgreSQL වලට import කරනවා විතරයි. Linux/Windows servers වල live logs කියවන්නේ නැහැ.

## Error fixes

- `password authentication failed` → `.env` හි user/password/db name එක Docker Compose file එකේ values වලට match වෙනවාද බලන්න.
- `address already in use` → පරණ Phase2 container එක තව 5434 භාවිතා කරනවාද check කරන්න. `docker stop` command එකෙන් volume delete වෙන්නේ නැහැ.
- `connection refused` → Docker container healthy ද `docker compose ps` බලන්න. `python -m check_db` හරහා check කරන්න.
- `npm install` fail → Node.js LTS සහ internet connection check කරන්න.

> වැදගත්: `docker compose down -v` භාවිතා කරන්න එපා. ඒකෙන් database volume එක delete වෙන්න පුළුවන්.
