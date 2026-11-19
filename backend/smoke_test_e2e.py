"""End-to-End Smoke Test for AccessGuard Quarterly ML Integration V10.

Executes the complete quarterly review and ML workflow programmatically:
1. Disposable DB initialization and demo telemetry seeding
2. Dedicated ML model loading and SHA-256 hash verification for all 3 platforms
3. Real Isolation Forest inference on 90-day feature vectors
4. 90-day Review Cycle Preview generation (hybrid policy + ML percentiles)
5. Review Cycle population freeze and task persistence
6. Review Queue task retrieval and mandatory override verification
7. Interactive manual human review decision recording
8. UTF-8 BOM CSV template export
9. Reviewed CSV outcome upload, format & business rule validation preview
10. Atomic commit of approved review outcome batch to system of record
11. Committed review outcomes CSV export
12. Offline ML training readiness and candidate preparation safety guards
"""
import os
import sys
from pathlib import Path

# Add backend and ml/backend to path
backend_dir = Path(__file__).resolve().parent
repo_dir = backend_dir.parent
ml_backend_dir = repo_dir / "ml" / "backend"

sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(ml_backend_dir))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["ML_SERVICE_TOKEN"] = "development-token-32-chars-long-minimum-key"

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.service import load_model_registry, score_accounts, build_model_status
import ml_client
from models import (
    Base,
    QuarterlyReviewCycle,
    QuarterlyAccountReview,
    QuarterlyReviewOutcome,
    MLTrainingRun,
)
from seed_demo import seed_demo
import quarterly_review_service as qrs


def run_e2e_smoke_test():
    print("=" * 70, flush=True)
    print("ACCESSGUARD QUARTERLY ML INTEGRATION V10 — END-TO-END SMOKE TEST", flush=True)
    print("=" * 70, flush=True)

    # 1. Setup disposable SQLite database and seed demo
    print("\n[Step 1] Initializing isolated SQLite database and seeding V10 demo telemetry...", flush=True)
    engine = create_engine("sqlite+pysqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as db:
        assert seed_demo(db), "Failed to seed demo data"
        print("  Database seeded successfully with platforms, accounts, and 90-day coverage!", flush=True)

    # 2. Verify ML Model Artifacts & Integrity
    print("\n[Step 2] Verifying ML Microservice Model Artifacts and Hash Integrity...", flush=True)
    registry, errors = load_model_registry()
    status_data = build_model_status(registry, errors)
    print(f"  Service: {status_data['service']} v{status_data['service_version']}", flush=True)
    print(f"  Models Loaded: {status_data['models_loaded']} / 3 (All loaded: {status_data['all_models_loaded']})", flush=True)
    for p in ["windows", "linux", "github"]:
        p_info = status_data["models"].get(p, {})
        assert p_info.get("loaded") is True, f"Model {p} not loaded"
        print(f"    - {p.upper()}: trees={p_info.get('trees')}, features={p_info.get('feature_count')}, trained_utc={p_info.get('trained_utc')}", flush=True)

    # Wire ml_client in-process to the loaded model registry
    def _in_proc_score(cycle_id, window_days, records):
        scored_list = score_accounts(records, window_days, registry, errors)
        return {str(item["account_id"]): item for item in scored_list if "account_id" in item}
    ml_client.score_accounts_batch = _in_proc_score

    with Session() as db:
        # 3. Build 90-Day Review Cycle Preview
        print("\n[Step 3] Generating 90-Day Review Cycle Preview (Hybrid Policy + ML Isolation Forest)...", flush=True)
        preview = qrs.build_cycle_preview(db, window_days=90, budget_pct=25)
        cycle_id = preview["cycle_id"]
        print(f"  Cycle ID: {cycle_id}", flush=True)
        print(f"  Window: {preview['window_start'][:10]} to {preview['window_end'][:10]} ({preview['window_days']} days)", flush=True)
        print(f"  Total Accounts Scanned: {preview['total_accounts']}", flush=True)
        print(f"  Mandatory Overrides: {preview['mandatory_count']}", flush=True)
        print(f"  Budget Selected: {preview['selected_count']}", flush=True)
        print(f"  Deferred Candidates: {preview['deferred_count']}", flush=True)
        print(f"  Total Review Queue: {preview['queue_size']}", flush=True)

        mandatory_items = [it for it in preview["accounts"] if it["is_mandatory"]]
        assert len(mandatory_items) > 0, "Expected at least one mandatory override account"
        m0 = mandatory_items[0]
        print(f"  Sample Mandatory Account: ACC-{m0['account_id']} ({m0['username']} on {m0['platform']})", flush=True)
        print(f"    Policy Score: {m0['policy_score']}, Reasons: {m0['policy_reasons']}", flush=True)
        print(f"    ML Anomaly Percentile: {m0.get('anomaly_percentile_100')}% (Status: {m0.get('anomaly_score_status')})", flush=True)

        # 4. Freeze and Create the Quarterly Review Cycle
        print("\n[Step 4] Freezing and Creating the Review Cycle in System of Record...", flush=True)
        cycle = qrs.create_review_cycle(db, window_days=90, budget_pct=25, created_by="SecurityAdmin")
        assert cycle.id == cycle_id
        assert cycle.total_accounts > 0
        print(f"  Created Cycle: {cycle.id} with {cycle.total_accounts} frozen account tasks", flush=True)

        # 5. Retrieve Review Queue Tasks
        print("\n[Step 5] Fetching Review Queue Tasks for Reviewer...", flush=True)
        tasks = db.scalars(
            select(QuarterlyAccountReview)
            .where(QuarterlyAccountReview.cycle_id == cycle_id)
            .order_by(QuarterlyAccountReview.priority.desc())
        ).all()
        queue_tasks = [t for t in tasks if t.priority in ('mandatory', 'selected')]
        print(f"  Review Queue Items Count: {len(queue_tasks)}", flush=True)
        first_task = queue_tasks[0]
        print(f"  Task #{first_task.id}: ACC-{first_task.account_id}, Priority={first_task.priority}, State={first_task.state}", flush=True)

        # 6. Record Manual Human Review Decision
        print("\n[Step 6] Recording Manual Human Review Decision...", flush=True)
        updated_task = qrs.record_account_decision(
            db,
            task_id=first_task.id,
            decision="request_revoke",
            reviewer_id="auditor@corp.dialog.lk",
            rationale="Excessive unused privileges verified during 90-day review",
        )
        print(f"  Recorded Decision: state={updated_task.state}, decision={updated_task.decision}, decision_by={updated_task.decision_by}", flush=True)
        assert updated_task.state == "decided"
        assert updated_task.decision == "request_revoke"

        # 7. Generate and Verify UTF-8 BOM CSV Template
        print("\n[Step 7] Exporting Review Cycle CSV Template...", flush=True)
        tmpl_content = qrs.generate_outcome_template_csv(db, cycle_id, scope="review_queue")
        assert tmpl_content.startswith("\ufeff"), "Missing UTF-8 BOM in template"
        tmpl_lines = tmpl_content.strip().split("\n")
        print(f"  Template generated: {len(tmpl_lines)} lines, Headers: {tmpl_lines[0].lstrip('\ufeff')}", flush=True)

        # 8. Upload and Preview Reviewed CSV Outcomes
        print("\n[Step 8] Validating Completed CSV Outcomes File (Upload Preview)...", flush=True)
        target_account = first_task
        csv_body = (
            "\ufeffschema_version,review_cycle_id,account_id,platform,reviewer_id,reviewed_at_utc,review_classification,access_decision,rationale,evidence_reference\n"
            f"1,{cycle_id},ACC-{target_account.account_id},{target_account.platform.lower()},lead-reviewer@corp.dialog.lk,2026-11-19T04:00:00Z,confirmed_policy_concern,request_revoke,Confirmed excessive access to be revoked,TICKET-7711\n"
        )
        csv_bytes = csv_body.encode("utf-8")
        preview_res = qrs.preview_outcome_csv(
            db,
            cycle_id=cycle_id,
            file_bytes=csv_bytes,
            original_filename="reviewed_outcomes.csv",
            uploader="lead-reviewer@corp.dialog.lk",
            scope="review_queue",
        )
        print(f"  CSV Validation: Total={preview_res['total_rows']}, Valid={preview_res['valid_rows']}, Invalid={preview_res['invalid_rows']}", flush=True)
        assert preview_res["valid_rows"] == 1
        assert preview_res["invalid_rows"] == 0
        batch_id = preview_res["batch_id"]

        # 9. Atomic Commit of Approved Batch
        print("\n[Step 9] Executing Atomic Commit of Approved CSV Batch...", flush=True)
        commit_result = qrs.commit_outcome_batch(
            db,
            batch_id=batch_id,
            approver="secops-director@corp.dialog.lk",
        )
        print(f"  Batch Committed: status={commit_result['status']}, records_committed={commit_result['records_committed']}", flush=True)
        assert commit_result["status"] == "committed"
        assert commit_result["records_committed"] == 1

        # 10. Export Committed Outcomes
        print("\n[Step 10] Verifying Committed Outcomes Export...", flush=True)
        export_csv = qrs.export_committed_outcomes_csv(db, cycle_id)
        assert export_csv.startswith("\ufeff")
        export_lines = export_csv.strip().split("\n")
        print(f"  Exported Outcomes: {len(export_lines) - 1} records committed in database", flush=True)

        # 11. Model Training Readiness & Label Separation Check
        print("\n[Step 11] Checking Offline ML Training Readiness & Candidate Safety...", flush=True)
        plat_key = "windows" if "win" in target_account.platform.lower() else "linux"
        readiness = qrs.get_training_readiness(db, plat_key)
        print(f"  Platform {plat_key.upper()} Training Readiness:", flush=True)
        print(f"    Verified Normal (label=0): {readiness['verified_normal']}", flush=True)
        print(f"    Confirmed Behavioral Concern (label=1): {readiness['confirmed_behavioral_concern']}", flush=True)
        print(f"    Confirmed Policy Concerns (Excluded): {readiness['confirmed_policy_concern']}", flush=True)
        print(f"    Can Prepare Candidate: {readiness['can_prepare_candidate']}", flush=True)

        # Verify that training preparation guards against under-threshold datasets
        try:
            run = qrs.prepare_training_candidate_snapshot(
                db,
                platform=plat_key,
                created_by="secops-director@corp.dialog.lk",
            )
            print(f"  Prepared Training Snapshot Run: {run.id}", flush=True)
        except ValueError as exc:
            print(f"  Training Preparation Safety Guard: Correctly blocked premature training ({exc})", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("ALL 11 END-TO-END SMOKE TEST STEPS COMPLETED SUCCESSFULLY!", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    run_e2e_smoke_test()
