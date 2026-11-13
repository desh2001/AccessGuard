"""Run 4 illustrative model-inference cases: python -m app.ml.demo"""
import json
from .model import load_model, model_path, score_rows


def examples() -> list[dict]:
    normal = dict(department="Engineering", platform="GitHub", permission_class="write",
                  sensitivity="medium", employee_status="active", account_status="active",
                  unmapped=0, outside_role=0, resource_use_observed=1, last_used_days=9,
                  last_login_observed=1, last_login_days=2)
    finance_admin = dict(normal, department="Finance", platform="Linux", permission_class="privileged",
                         sensitivity="critical", outside_role=1, last_used_days=110, last_login_days=121)
    orphan = dict(normal, department="Unknown", platform="Windows AD", permission_class="privileged",
                  sensitivity="critical", employee_status="unknown", unmapped=1, outside_role=0,
                  resource_use_observed=0, last_used_days=0, last_login_observed=0, last_login_days=0)
    missing_use = dict(normal, department="Finance", platform="Linux", permission_class="read",
                       resource_use_observed=0, last_used_days=0)
    return [dict(example=name, **row) for name, row in [
        ("typical_engineering_access", normal),
        ("finance_admin_stale", finance_admin),
        ("orphaned_privileged_account", orphan),
        ("missing_resource_use_evidence_not_inactivity", missing_use),
    ]]


def main() -> None:
    artifact = load_model()
    if artifact is None:
        raise SystemExit(f"No model at {model_path()}. Run: python -m app.ml.train --csv ml_data/synthetic_demo.csv")
    cases = examples()
    predictions = score_rows(cases, artifact)
    for case, prediction in zip(cases, predictions):
        print(json.dumps({"case": case["example"], **prediction,
                          "note": "rarity percentile is not a threat probability"}))


if __name__ == "__main__":
    main()
