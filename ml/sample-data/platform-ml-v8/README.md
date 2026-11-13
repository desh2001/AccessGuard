# Collector-to-ML event contract (V8)

**Send normalized events, not raw pasted OS logs.** Teammate 1 maps events from authorized Windows/Linux/GitHub sources and imports the supported CSV table schemas (or invokes the API/data pipeline). Teammate 2 provides identity, entitlement, approval and review API integration. The ML workstream receives authorized account-cycle features through PostgreSQL.

## Required inputs

1. `employees`: code, name, email, department, job_title, status; optional manager_username.
2. `accounts`: platform, username, employee_code, status. Use canonical `Windows AD`, `Linux`, `GitHub`, or documented aliases.
3. `entitlements`: platform, username, resource, permission, sensitivity; optional source,active,last_used_at,evidence_source.
4. `activities`: platform,username,resource,event_type,occurred_at,source.
5. `coverage`: platform,event_type,start_at,end_at,source,attested_by. Coverage is independently attested; an event in a log is **not** coverage attestation.
6. AD/HR snapshots and group-to-resource mappings from V6 data contract. Every unreviewed transfer remains mandatory even if the ML model disagrees.

## Supported normalized event types

| Source | Example raw record | Event type to import | Interpretation |
|---|---|---|---|
| Windows | 4624 or supported sign-in | `login_success` | Authentication, **not** entitlement use |
| Windows | 4625 | `login_failed` | Authentication failure |
| Windows | 4672 (special privileges assigned) | `windows_privileged_logon` | Extra Windows ML activity context; not proof of misuse |
| Linux | SSH/PAM successful auth | `login_success` | Authentication |
| Linux | SSH/PAM failure | `login_failed` | Authentication failure |
| Linux | Trusted sudo command audit | `linux_sudo` | Linux ML activity context; not proof of unauthorised use |
| GitHub | Audited repository activity, attributable to account | `github_repo_activity` | GitHub ML activity context; requires appropriate enterprise API/audit source |
| Any | Verified protected resource action with matching active grant | `resource_use` | Evidence of entitlement-associated resource use, only when trustworthy |
| Any | Authorized access grant change | `permission_changed` | Permission change context |
| Any | Browser music or general browsing | **Do not map to managed access risk** | Not an access entitlement failure |

`github_repo_activity` is **not** equivalent to `resource_use` unless the adapter independently verifies it is evidence of using an active resource grant and issues a separate vetted `resource_use` event. Likewise Windows 4672 is not a privilege abuse determination, and Linux sudo use can be legitimate.

## Coverage and validation

For each source, collectors can attest optional event-class coverage separately (`windows_privileged_logon`, `linux_sudo`, `github_repo_activity`). The ML features distinguish unavailable optional logs using a `*_coverage_known` flag, and the main resource-use coverage remains mandatory to score a 90-day window. A platform's coverage is not automatically proof that every resource or permission is fully instrumented; inventory completeness and per-application logging need separate validation. Unmapped applications (e.g. GitLab) are scored rules-only until their own model is trained and validated.

## Model training and review cycle

```
cd backend
python -m app.ml.periodic_generate --rows 1800 --out ml_data/periodic_synthetic.csv
python -m app.ml.platform_train --csv ml_data/periodic_synthetic.csv
python -m app.ml.platform_benchmark --budget 10
python -m app.ml.competition_demo --accounts 1200 --budget 10 --with-ml
python -m pytest -q
```

For a real pilot, replace the fabricated training labels with independently reviewed account-cycle decisions; freeze model and thresholds before each manual review, compare blind reviews, tune on pilot A only, and verify on untouched pilot B. No automatic access deletion or automatic certification.
