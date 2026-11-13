# Research Experiment Plan — AccessGuard

## Research question

Can combining explainable rule-based access governance risk flags with an unsupervised anomaly rank reduce manual review effort without increasing false-positive removals, compared with periodic manual access reviews?

This is a **hypothesis**, not an established research gap. A literature review of current IGA, UEBA, access certification, anomaly detection and identity resolution studies is required to prove a specific gap.

## Baseline and proposed method

- Baseline A: Manual periodic review by reviewer given identical entitlement inventories.
- Baseline B: Transparent rules (departed owner, privileged role, cross-department role, missing owner, use-evidence age only where logging is adequate).
- Proposed: Transparent rules + Isolation Forest anomaly percentile prioritization, with explanation and uncertainty warnings.
- Comparator should use **same test cases** and randomized/order-balanced reviewer assignments to reduce bias.

## Dataset plan

1. Collect fully synthetic employee, role, department, technical account, permission and event records (seed script included).
2. Independently define ground-truth scenarios: authorized exception, known offboarding error, cross-team shared administrator, legitimate on-call admin, unknown owner, fake log-coverage gaps.
3. Split by **employee/account group** rather than random rows, to avoid granting nearly duplicate identity-derived rows to train/test.
4. Label using documented access policies and expert/supervisor review. Keep sensitive real HR data out of this demo.
5. Separate observed non-use from missing telemetry; missing logs must never automatically label excess permission.
6. Evaluate by department, role, age of entitlement, sparse log coverage and exception type.

## Evaluation metrics

- Precision, Recall, F1 and False Positive Rate for escalation decisions with gold-standard reviewer labels.
- Precision@K / Recall@K for prioritized review queue; PR-AUC when suitable.
- Minutes per entitlement review, review decision quality and full remediation time **within the simulated workflow**.
- Identity mapping accuracy and manual verification effort.
- Reviewer disagreement rate; reason/explanation usability scores.
- Audit completeness = number of decisions with required evidence / all decisions.

## ML cautions

Isolation Forest in `ai_engine.py` trains on the current synthetic snapshot and computes a **relative percentile**. It has no calibrated likelihood of misuse. Model importance and the text reasons listed in UI are from transparent rule features, not a causal explanation of the black-box score. A publication-quality evaluation requires independent labels, baselines, ablations and confidence intervals. This prototype does not claim measured security improvement.

## Production architecture changes required

- Real OIDC/SSO sign-in and backend-enforced RBAC (`viewer`,`reviewer`,`approver`,`admin`), CSRF/session protection, secure secrets, rate limits.
- Read-only scoped connectors plus connector health, error handling, pagination coverage and freshness SLAs.
- Authoritative HR join/leave role changes, approval chain, conflict-of-interest separation, least-privilege remediation credentials.
- Durable queue for reconciliation; verified real-source post-change checks, rollback/compensation, and tested idempotency.
- Tamper-resistant audit export and change management, immutable retention policy, consent and data minimization.
- PostgreSQL backup/restore drills and security testing.
