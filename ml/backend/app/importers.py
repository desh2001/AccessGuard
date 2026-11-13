import csv
import io
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import Employee, Account, Entitlement, Activity, ActivityCoverage, DirectorySnapshot, ADGroupMembership, EmployeeTransfer, ADGroupChange, ADGroupCatalog, ADGroupMembershipHistory, utcnow

REQUIRED = {
    "employees": {"code", "name", "email", "department", "job_title", "status"},
    "accounts": {"platform", "username", "employee_code", "status"},
    "entitlements": {"platform", "username", "resource", "permission", "sensitivity"},
    "activities": {"platform", "username", "resource", "event_type", "occurred_at", "source"},
    "coverage": {"platform", "event_type", "start_at", "end_at", "source", "attested_by"},
    "ad_groups": {"employee_code", "group_name", "active", "source"},
    "ad_group_catalog": {"organization_key", "directory_key", "group_key", "display_name", "group_kind", "access_relevance", "privilege_tier", "risk_tier", "approved_by", "source", "policy_version"},
    "ad_group_changes": {"employee_code", "group_name", "action", "occurred_at", "source"},
    "employee_transfers": {"employee_code", "occurred_at", "from_department", "to_department", "from_manager", "to_manager", "source"},
    "directory_snapshots": {"employee_code", "snapshot_at", "reporting_manager", "org_unit", "ad_department", "groups_complete", "transfer_history_complete", "source"},
}

def parse_dt(value):
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return (parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed).replace(tzinfo=None)
    except ValueError:
        raise ValueError(f"Invalid date: {value}. Use ISO-8601 format")

def directory_identity(org, directory, key, name):
    org = (org or "demo").strip() or "demo"
    directory = (directory or "primary").strip() or "primary"
    key = (key or "").strip() or "name:" + (name or "").strip().casefold()
    if not (org and directory and key and len(key) <= 220):
        raise ValueError("Invalid group directory identity")
    return org, directory, key


def import_csv(db: Session, kind: str, data: bytes):
    if kind not in REQUIRED:
        raise HTTPException(404, "Unknown CSV dataset")
    if len(data) > 2_000_000:
        raise HTTPException(413, "CSV upload limit is 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        if not reader.fieldnames or not REQUIRED[kind].issubset(set(reader.fieldnames)):
            raise HTTPException(422, f"Required columns: {', '.join(sorted(REQUIRED[kind]))}")
        rows = list(reader)
        if len(rows) > 3000:
            raise HTTPException(413, "Max 3000 rows per file")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8")
    count = 0
    try:
        for i, row in enumerate(rows, 2):
            if kind == "employees":
                obj = db.query(Employee).filter_by(code=row["code"].strip()).first()
                if not obj:
                    obj = Employee(code=row["code"].strip()); db.add(obj)
                for k in ("name", "email", "department", "job_title", "status"):
                    setattr(obj, k, row[k].strip())
                obj.manager_username = row.get("manager_username", "reviewer").strip() or "reviewer"
            elif kind == "accounts":
                employee_code = row["employee_code"].strip()
                emp = db.query(Employee).filter_by(code=employee_code).first() if employee_code else None
                if employee_code and not emp:
                    raise ValueError(f"Unknown employee_code {employee_code}")
                obj = db.query(Account).filter_by(platform=row["platform"].strip(), username=row["username"].strip()).first()
                if not obj:
                    obj = Account(platform=row["platform"].strip(), username=row["username"].strip()); db.add(obj)
                obj.employee_id = emp.id if emp else None
                obj.status = row["status"].strip()
                obj.last_login = parse_dt(row.get("last_login"))
                obj.last_login_source = row.get("last_login_source", "csv")
                obj.synced_at = utcnow()
            elif kind == "ad_group_catalog":
                group_name = row["display_name"].strip()
                org, directory, key = directory_identity(row["organization_key"], row["directory_key"], row["group_key"], group_name)
                group_kind = row["group_kind"].strip().lower()
                relevance = row["access_relevance"].strip().lower()
                privilege = row["privilege_tier"].strip().lower()
                risk = row["risk_tier"].strip().lower()
                if group_kind not in {"security", "distribution", "m365", "other", "unknown"}:
                    raise ValueError("Unknown group_kind")
                if relevance not in {"access", "non_access", "unknown"}:
                    raise ValueError("Invalid access_relevance")
                if privilege not in {"privileged", "standard", "unknown"}:
                    raise ValueError("Invalid privilege_tier")
                if risk not in {"critical", "high", "medium", "low", "unknown"}:
                    raise ValueError("Invalid risk_tier")
                if not group_name or not row["approved_by"].strip() or not row["source"].strip():
                    raise ValueError("Catalog requires group display name, policy approver and source")
                if relevance == "non_access" and privilege == "privileged":
                    raise ValueError("Non-access group cannot grant privileged access")
                when = parse_dt(row.get("effective_at")) or utcnow()
                if when > utcnow():
                    raise ValueError("Future effective_at is not allowed")
                obj = db.query(ADGroupCatalog).filter_by(organization_key=org, directory_key=directory, group_key=key).first()
                if obj and when < obj.effective_at:
                    raise ValueError("Cannot overwrite catalog with older policy")
                if obj is None:
                    obj = ADGroupCatalog(organization_key=org, directory_key=directory, group_key=key)
                    db.add(obj)
                obj.display_name = group_name
                obj.group_kind = group_kind
                obj.access_relevance = relevance
                obj.privilege_tier = privilege
                obj.risk_tier = risk
                obj.resource_scope = (row.get("resource_scope") or "").strip() or None
                obj.allowed_departments = [v.strip() for v in (row.get("allowed_departments") or "").split("|") if v.strip()]
                obj.approved_by = row["approved_by"].strip()
                obj.source = row["source"].strip()
                obj.policy_version = row["policy_version"].strip()
                obj.effective_at = when
                obj.updated_at = utcnow()
            elif kind in {"ad_groups", "ad_group_changes", "employee_transfers", "directory_snapshots"}:
                code = row["employee_code"].strip()
                emp = db.query(Employee).filter_by(code=code).first()
                if emp is None:
                    raise ValueError(f"Unknown employee_code {code}: import employees first")
                if not row.get("source", "").strip():
                    raise ValueError("source is required")
                if kind == "ad_groups":
                    group_name = row["group_name"].strip()
                    if not group_name:
                        raise ValueError("group_name is required")
                    org, directory, key = directory_identity(row.get("organization_key"), row.get("directory_key"), row.get("group_key"), group_name)
                    obj = db.query(ADGroupMembership).filter_by(employee_id=emp.id, organization_key=org,
                                                                  directory_key=directory, group_key=key).first()
                    event_active = row["active"].strip().lower() in {"true", "1", "yes"}
                    event_source = row["source"].strip()
                    when = parse_dt(row.get("synced_at")) or utcnow()
                    if when > utcnow():
                        raise ValueError("Group synced_at cannot be in the future")
                    if obj is None:
                        obj = ADGroupMembership(employee_id=emp.id, organization_key=org, directory_key=directory,
                                                group_key=key, group_name=group_name)
                        db.add(obj)
                    if obj.synced_at is None or when >= obj.synced_at:
                        # Older imports backfill history but cannot rewind the
                        # latest materialized AD membership snapshot.
                        obj.group_name = group_name
                        obj.active = event_active
                        obj.privileged = False  # Never trust raw privilege flags.
                        obj.source = event_source
                        obj.synced_at = when
                    # Append dated group observations; do not silently rewrite
                    # historical quarterly features when the newest CSV arrives.
                    historical = db.query(ADGroupMembershipHistory).filter_by(
                        employee_id=emp.id, organization_key=org, directory_key=directory,
                        group_key=key, observed_at=when).first()
                    if historical is None:
                        db.add(ADGroupMembershipHistory(employee_id=emp.id, organization_key=org,
                            directory_key=directory, group_key=key, display_name=group_name,
                            active=event_active, observed_at=when, source=event_source))
                    elif historical.active != event_active:
                        raise ValueError('Conflicting AD group snapshot with identical observed_at')
                elif kind == "directory_snapshots":
                    snapshot_at = parse_dt(row["snapshot_at"])
                    if not snapshot_at or snapshot_at > utcnow():
                        raise ValueError("snapshot_at must be present and not in the future")
                    obj = db.get(DirectorySnapshot, emp.id)
                    if obj is not None and snapshot_at < obj.snapshot_at:
                        raise ValueError("Cannot overwrite a newer AD snapshot with an older snapshot")
                    if obj is not None and snapshot_at > obj.snapshot_at:
                        # A change in AD reporting scope is a signal for human
                        # re-certification, NOT proof that an HR transfer occurred.
                        incoming_manager = row["reporting_manager"].strip() or None
                        incoming_department = row["ad_department"].strip() or None
                        incoming_ou = row["org_unit"].strip() or None
                        if ((obj.reporting_manager and incoming_manager and obj.reporting_manager != incoming_manager)
                                or (obj.ad_department and incoming_department and obj.ad_department != incoming_department)
                                or (obj.org_unit and incoming_ou and obj.org_unit != incoming_ou)):
                            previous_event = db.query(EmployeeTransfer).filter_by(
                                employee_id=emp.id, occurred_at=snapshot_at, source="ad_snapshot_diff").first()
                            if previous_event is None:
                                db.add(EmployeeTransfer(
                                    employee_id=emp.id, occurred_at=snapshot_at,
                                    from_department=obj.ad_department, to_department=incoming_department,
                                    from_manager=obj.reporting_manager, to_manager=incoming_manager,
                                    from_org_unit=obj.org_unit, to_org_unit=incoming_ou,
                                    source="ad_snapshot_diff"))
                    if obj is None:
                        obj = DirectorySnapshot(employee_id=emp.id)
                        db.add(obj)
                    obj.snapshot_at = snapshot_at
                    obj.reporting_manager = row["reporting_manager"].strip() or None
                    obj.org_unit = row["org_unit"].strip() or None
                    obj.ad_department = row["ad_department"].strip() or None
                    obj.groups_complete = row["groups_complete"].strip().lower() in {"true", "1", "yes"}
                    obj.transfer_history_complete = row["transfer_history_complete"].strip().lower() in {"true", "1", "yes"}
                    obj.source = row["source"].strip()
                elif kind == "employee_transfers":
                    occurred = parse_dt(row["occurred_at"])
                    if not occurred or occurred > utcnow():
                        raise ValueError("Transfer occurred_at must be valid and not in the future")
                    obj = db.query(EmployeeTransfer).filter_by(employee_id=emp.id, occurred_at=occurred, source=row["source"].strip()).first()
                    if obj is None:
                        obj = EmployeeTransfer(employee_id=emp.id, occurred_at=occurred, source=row["source"].strip())
                        db.add(obj)
                    for column in ("from_department", "to_department", "from_manager", "to_manager", "from_org_unit", "to_org_unit"):
                        setattr(obj, column, (row.get(column) or "").strip() or None)
                elif kind == "ad_group_changes":
                    action = row["action"].strip().lower()
                    occurred = parse_dt(row["occurred_at"])
                    if action not in {"added", "removed"} or not occurred or occurred > utcnow():
                        raise ValueError("Group change must have action added/removed and valid occurred_at")
                    obj = db.query(ADGroupChange).filter_by(employee_id=emp.id, group_name=row["group_name"].strip(), occurred_at=occurred, action=action).first()
                    if obj is None:
                        db.add(ADGroupChange(employee_id=emp.id, group_name=row["group_name"].strip(),
                                             occurred_at=occurred, action=action, source=row["source"].strip()))
            elif kind == "coverage":
                start = parse_dt(row["start_at"])
                end = parse_dt(row["end_at"])
                if not start or not end or end <= start:
                    raise ValueError("Coverage timestamps must have end after start")
                coverage_type = row["event_type"].strip().lower()
                supported = {"resource_use", "windows_privileged_logon",
                             "linux_sudo", "github_repo_activity"}
                if coverage_type not in supported:
                    raise ValueError("Unsupported coverage event type")
                from .ml.platform_models import platform_key
                expected_platform = {"windows_privileged_logon": "windows",
                                     "linux_sudo": "linux", "github_repo_activity": "github"}
                if coverage_type in expected_platform and platform_key(row["platform"]) != expected_platform[coverage_type]:
                    raise ValueError("Coverage type does not belong to this platform")
                if not row["attested_by"].strip() or not row["source"].strip():
                    raise ValueError("Provide collector source and responsible coverage attester")
                db.add(ActivityCoverage(platform=row["platform"].strip(),
                    event_type=coverage_type, start_at=start, end_at=end,
                    source=row["source"].strip(), attested_by=row["attested_by"].strip()))
            elif kind in {"entitlements", "activities"}:
                acc = db.query(Account).filter_by(platform=row["platform"].strip(), username=row["username"].strip()).first()
                if not acc:
                    raise ValueError("Unknown account: import accounts first")
                if kind == "entitlements":
                    resource, permission = row["resource"].strip(), row["permission"].strip()
                    obj = db.query(Entitlement).filter_by(account_id=acc.id, resource=resource, permission=permission).first()
                    if not obj:
                        obj = Entitlement(account_id=acc.id, resource=resource, permission=permission); db.add(obj)
                    obj.sensitivity = row["sensitivity"].strip().lower()
                    obj.source = row.get("source", "csv") or "csv"
                    obj.active = row.get("active", "true").strip().lower() != "false"
                    obj.last_used_at = parse_dt(row.get("last_used_at"))
                    obj.evidence_source = (row.get("evidence_source") or None)
                else:
                    obj = Activity(account_id=acc.id, resource=row["resource"].strip(), event_type=row["event_type"].strip(), occurred_at=parse_dt(row["occurred_at"]), source=row["source"].strip())
                    db.add(obj)
                    # Only explicit resource-use events can update entitlement use.
                    if obj.event_type.lower() == "resource_use":
                        for e in db.query(Entitlement).filter_by(account_id=acc.id, resource=obj.resource).all():
                            if not e.last_used_at or e.last_used_at < obj.occurred_at:
                                e.last_used_at = obj.occurred_at
                                e.evidence_source = obj.source
            db.flush()
            count += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"CSV row {i if rows else 0}: {str(exc)[:250]}")
    return count
