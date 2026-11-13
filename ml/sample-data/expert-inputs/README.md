# Fictional sample input bundle

All accounts and identities in this folder are synthetic. Dates demonstrate a 90-day window ending in early November 2026. Recreate coverage attestations for your actual review window rather than copying these dates. Never mark 100% log coverage without evidence from the collecting system.

Import in this order: `employees`, `accounts`, `entitlements`, `directory_snapshots`, `ad_groups`, `employee_transfers`, `ad_group_changes`, `activities`, `coverage`.

Run from `backend/` after configuring DATABASE_URL:

```bash
for kind in employees accounts entitlements directory_snapshots ad_groups employee_transfers ad_group_changes activities coverage; do
  python -m app.ml.source_ingest --kind "$kind" --csv "../sample-data/expert-inputs/$kind.csv"
done
```

`app.ml.source_ingest` also accepts `--mysql-table name` and environment variable `AEGIS_SOURCE_MYSQL_URL` using **read-only** credentials after an approved SQL dump has been restored into an isolated MySQL staging database. It never executes SQL dump text. For column renaming, use `--column-map '{"employee_id":"code","full_name":"name"}'`.

The `privileged` group classification must be verified using a group entitlement policy, not guessed from its string name. Importing AD snapshots consecutively can also derive scope-change events when manager, department, or organizational unit changes. The snapshot flags `groups_complete` and `transfer_history_complete` must only be true when the source owner attests to complete coverage; otherwise use `false`.
