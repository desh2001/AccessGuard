"""Reproducible SYNTHETIC, policy-derived scenarios: training demo only.

Labels are constructed from our scenarios and therefore cannot establish
real-world performance. Never present metrics from this file as security efficacy.
"""
import argparse
import csv
import random
from pathlib import Path
from .features import FEATURE_COLUMNS

DEPARTMENTS = ["Finance", "Engineering", "HR", "Sales", "IT"]
PLATFORMS = ["Linux", "GitHub", "Windows AD"]


def generate_rows(normal: int = 1000, anomalous: int = 250, seed: int = 42) -> list[dict]:
    randomizer = random.Random(seed)
    rows = []
    for i in range(normal + anomalous):
        is_anomaly = int(i >= normal)
        dept = randomizer.choice(DEPARTMENTS)
        platform = randomizer.choice(PLATFORMS)
        permission = randomizer.choices(["read", "write", "privileged"], [0.65, 0.30, 0.05])[0]
        sensitivity = randomizer.choices(["low", "medium", "high", "critical"], [0.23, 0.56, 0.18, 0.03])[0]
        observed = int(randomizer.random() > 0.15)
        last_used = randomizer.randrange(0, 52) if observed else 0
        login_observed = int(randomizer.random() > 0.08)
        login_days = randomizer.randrange(0, 60) if login_observed else 0
        row = {
            "department": dept, "platform": platform, "permission_class": permission,
            "sensitivity": sensitivity, "employee_status": "active", "account_status": "active",
            "unmapped": 0, "outside_role": 0,
            "resource_use_observed": observed, "last_used_days": last_used,
            "last_login_observed": login_observed, "last_login_days": login_days,
            "label": is_anomaly, "scenario": "routine_entitlement",
            "group_id": f"demo-employee-{i // 3:05d}",
        }
        if is_anomaly:
            scenario = randomizer.choice(["unmapped_privileged", "outside_department_privileged",
                                          "terminated_account", "stale_privileged_access"])
            row["scenario"] = scenario
            if scenario == "unmapped_privileged":
                row.update(unmapped=1, employee_status="unknown", department="Unknown",
                           permission_class="privileged", sensitivity="critical", outside_role=0)
            elif scenario == "outside_department_privileged":
                row.update(outside_role=1, permission_class="privileged", sensitivity="high")
            elif scenario == "terminated_account":
                row.update(employee_status="inactive", account_status="active", sensitivity="high")
            else:
                row.update(permission_class="privileged", sensitivity="critical",
                           resource_use_observed=1, last_used_days=randomizer.randint(95, 300),
                           last_login_observed=1, last_login_days=randomizer.randint(90, 270))
        rows.append(row)
    randomizer.shuffle(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic examples for a classroom ML demo")
    parser.add_argument("--out", type=Path, default=Path("ml_data/synthetic_demo.csv"))
    parser.add_argument("--normal", type=int, default=1000)
    parser.add_argument("--anomalous", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.normal < 120 or args.anomalous < 30:
        parser.error("Use >=120 routine cases and >=30 anomalous cases for the illustration")
    rows = generate_rows(args.normal, args.anomalous, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FEATURE_COLUMNS + ["label", "scenario", "group_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} SYNTHETIC rows: {args.out}")


if __name__ == "__main__":
    main()
