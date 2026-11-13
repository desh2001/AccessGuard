"""Clear synthetic / mock demo data from the AccessGuard database.

Usage:
    python clear_db.py
    python clear_db.py --all   (also clears system definitions)
"""
from __future__ import annotations
import sys
from sqlalchemy import delete
from database import SessionLocal
from models import (
    ActivityEvent, Review, AccessGrant, Account,
    Identity, ConnectorRun, AuditLog, System
)


def clear_database(clear_systems: bool = False):
    with SessionLocal() as db:
        print("Clearing mock and demo data from database...")
        db.execute(delete(ActivityEvent))
        db.execute(delete(Review))
        db.execute(delete(AccessGrant))
        db.execute(delete(Account))
        db.execute(delete(Identity))
        db.execute(delete(ConnectorRun))
        db.execute(delete(AuditLog))

        if clear_systems:
            db.execute(delete(System))
            print("Cleared systems table.")

        db.commit()
        print("All mock identities, accounts, grants, activity events, reviews, and logs have been cleared successfully!")


if __name__ == '__main__':
    clear_sys = '--all' in sys.argv
    clear_database(clear_systems=clear_sys)

