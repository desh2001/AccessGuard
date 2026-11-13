import os
from datetime import timedelta
from sqlalchemy.orm import Session
from .models import Employee, Account, Entitlement, Activity, ActivityCoverage, User, utcnow
from .security import hash_password
from .risk import recompute

def seed_demo(db: Session):
    if db.query(Employee).first():
        return
    admin_pwd = os.environ.get("DEMO_ADMIN_PASSWORD")
    reviewer_pwd = os.environ.get("DEMO_REVIEWER_PASSWORD")
    if not admin_pwd or not reviewer_pwd:
        raise RuntimeError("DEMO_ADMIN_PASSWORD and DEMO_REVIEWER_PASSWORD must be set when SEED_DEMO=true")
    db.add_all([
        User(username="admin", display_name="System Administrator", role="admin", password_hash=hash_password(admin_pwd)),
        User(username="reviewer", display_name="Access Review Manager", role="reviewer", password_hash=hash_password(reviewer_pwd)),
    ])
    names = [
        ("EMP-1001", "Olivia Chen", "olivia@example.test", "Engineering", "Backend Engineer", "active"),
        ("EMP-1002", "James Wilson", "james@example.test", "Finance", "Financial Analyst", "active"),
        ("EMP-1003", "Sophia Patel", "sophia@example.test", "HR", "HR Manager", "active"),
        ("EMP-1004", "Noah Williams", "noah@example.test", "IT", "Systems Engineer", "active"),
        ("EMP-1005", "Emma Davis", "emma@example.test", "Sales", "Account Executive", "active"),
        ("EMP-1006", "Liam Brown", "liam@example.test", "Engineering", "DevOps Engineer", "active"),
        ("EMP-1007", "Mia Taylor", "mia@example.test", "Finance", "Accountant", "inactive"),
        ("EMP-1008", "Ethan Moore", "ethan@example.test", "Engineering", "QA Engineer", "active"),
        ("EMP-1009", "Ava Lee", "ava@example.test", "Sales", "Sales Ops", "active"),
        ("EMP-1010", "Lucas Garcia", "lucas@example.test", "IT", "Security Analyst", "active"),
        ("EMP-1011", "Isabella Martin", "isabella@example.test", "HR", "Recruiter", "active"),
        ("EMP-1012", "Henry Walker", "henry@example.test", "Engineering", "Frontend Engineer", "active"),
    ]
    now = utcnow()
    for i, (code, name, email, department, title, status) in enumerate(names):
        emp = Employee(code=code, name=name, email=email, department=department, job_title=title, status=status, manager_username="reviewer")
        db.add(emp); db.flush()
        platform = ["GitHub", "Linux", "Windows AD"][i % 3]
        account = Account(employee_id=emp.id, platform=platform, username=email.split("@")[0], status="active", last_login=now-timedelta(days=(i*17)%140), last_login_source="synthetic demo")
        db.add(account); db.flush()
        typical = {"Engineering": ("github:platform-api", "write"), "Finance": ("finance:erp", "read"), "HR": ("hr:people", "write"), "IT": ("linux:production", "admin"), "Sales": ("crm:sales", "read")}
        resource, permission = typical[department]
        db.add(Entitlement(account_id=account.id, resource=resource, permission=permission, sensitivity="high" if permission == "admin" else "medium", source="synthetic demo", last_used_at=now-timedelta(days=(i*9)%105), evidence_source="synthetic demo"))
        db.add(Entitlement(account_id=account.id, resource="shared:intranet", permission="read", sensitivity="low", source="synthetic demo", last_used_at=now-timedelta(days=i*3), evidence_source="synthetic demo"))
        if i in {1, 3, 6, 9}:
            db.add(Entitlement(account_id=account.id, resource="dev:production-db", permission="admin", sensitivity="critical", source="synthetic demo", last_used_at=now-timedelta(days=100+i*5), evidence_source="synthetic demo"))
        if i % 4 == 0:
            db.add(Entitlement(account_id=account.id, resource="github:legacy-repo", permission="maintain", sensitivity="medium", source="synthetic demo", last_used_at=None))
    orphan = Account(employee_id=None, platform="Linux", username="legacy-svc-unknown", last_login=now-timedelta(days=215), last_login_source="synthetic demo")
    db.add(orphan); db.flush()
    db.add(Entitlement(account_id=orphan.id, resource="linux:production", permission="root", sensitivity="critical", last_used_at=None, source="synthetic demo"))
    # Synthetic competition demonstration corresponding to the expert's example.
    # Do not use these fictional identities to claim real enterprise performance.
    db.add(ActivityCoverage(platform='Demo Linux', event_type='resource_use',
        start_at=now-timedelta(days=90),end_at=now,source='synthetic_demo_full_coverage',
        attested_by='demo_seed'))
    sample_people = [
        ('EMP-DEMO-01','Chamila Demo','chamila.demo@example.test','IT','Systems Engineer','active','read',True),
        ('EMP-DEMO-02','Rishan Demo','rishan.demo@example.test','IT','Former Engineer','inactive','admin',False),
        ('EMP-DEMO-03','Demo Account Three','third.demo@example.test','Finance','Analyst','active','admin',False),
    ]
    for code, name, email, dept, role, hr_status, perm, has_usage in sample_people:
        employee=Employee(code=code,name=name,email=email,department=dept,job_title=role,
                          status=hr_status,manager_username='reviewer')
        db.add(employee);db.flush()
        account=Account(employee_id=employee.id,platform='Demo Linux',username=email.split('@')[0],
                        status='active',last_login_source='synthetic_demo')
        db.add(account);db.flush()
        resource='demo:development-database' if dept=='Finance' else 'demo:application-server'
        grant=Entitlement(account_id=account.id,resource=resource,permission=perm,
                          sensitivity='critical' if perm=='admin' else 'low',source='synthetic_demo')
        db.add(grant);db.flush()
        if has_usage:
            for days in (3,12,25,43,70):
                when=now-timedelta(days=days)
                db.add(Activity(account_id=account.id,resource=resource,event_type='resource_use',
                                occurred_at=when,source='synthetic_demo'))
            grant.last_used_at=now-timedelta(days=3)
            grant.evidence_source='synthetic_demo'
    db.flush()
    recompute(db)
    db.commit()
