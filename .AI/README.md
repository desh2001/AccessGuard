# AccessGuard — AI Context & System Architecture Documentation

Welcome to the **`.AI`** architectural and implementation reference directory for **AccessGuard**.

This directory serves as the centralized, authoritative knowledge base for artificial intelligence assistants, developers, security engineers, and researchers working on or evaluating the AccessGuard codebase.

---

## 📚 Document Index

| Document | Primary Focus | Description |
|---|---|---|
| [**`PROJECT_ARCHITECTURE.md`**](file:///e:/AccessGuard/.AI/PROJECT_ARCHITECTURE.md) | **System Architecture & Design** | Ecosystem topology, subsystem boundaries (FastAPI, React 19, Dialog Access Log, Dialog Final ML), communication protocols, networking, deployment, and security isolation guardrails. |
| [**`FEATURE_IMPLEMENTATIONS.md`**](file:///e:/AccessGuard/.AI/FEATURE_IMPLEMENTATIONS.md) | **Core Feature Capabilities** | Exhaustive functional catalog covering all 14 governance views (Identities, Accounts, Entitlements, AI Risk Analysis, Reviews, Simulated Remediation, Activity Evidence, Offboarding, Integrations, Audit). |
| [**`DATABASE_SCHEMA.md`**](file:///e:/AccessGuard/.AI/DATABASE_SCHEMA.md) | **Relational Schema & Models** | Complete PostgreSQL 17 ERD, ORM models (SQLAlchemy 2.0), relational constraints, foreign key cascades, check validations, lifecycle status flows, and query patterns. |
| [**`ML_IMPLEMENTATION.md`**](file:///e:/AccessGuard/.AI/ML_IMPLEMENTATION.md) | **Machine Learning & AI Engine** | Dual-tier ML architecture, Aegis V8 3-platform models (Windows AD, Linux PAM, GitHub), feature engineering vectors, peer group anomaly detection, Isolation Forest math, blended scoring formula, and XAI guardrails. |
| [**`FUTURE_IMPLEMENTATIONS.md`**](file:///e:/AccessGuard/.AI/FUTURE_IMPLEMENTATIONS.md) | **Roadmap & Production Blueprint** | Technical roadmap transitioning AccessGuard from a research laboratory to a hardened enterprise IGA platform (OIDC/SAML, real SCIM connectors, Graph Neural Networks, GRC compliance mappings). |

---

## 🏛️ System Summary

**AccessGuard** is a local-first research and demonstration platform for **AI-assisted Identity Governance and Administration (IGA)**.

### Subsystems Overview
1. **AccessGuard Core Backend (`backend/`):** FastAPI REST API (port `8000`), SQLAlchemy 2.0 ORM, PostgreSQL 17 (port `5434`), rule-based risk scoring, campaign manager, simulated non-destructive remediation.
2. **AccessGuard Core Frontend (`frontend/`):** React 19 single-page dashboard (port `5173`), Tailwind CSS v4, Lucide icons, Recharts visualization.
3. **Dialog Access Log Subsystem (`accesslog-main/`):** Syslog TCP listener (port `5514`), device explorer API (port `8002`), log normalization, Sentinel Universal Ingestion API sync.
4. **Dialog Final ML Microservice (`ml/` & `backend/mock_ml_service.py`):** Aegis V8 multi-platform Isolation Forest models (Windows AD, Linux, GitHub) evaluating peer-group entitlement anomalies (port `8001`).

---

## 🛡️ Research & Safety Constraints

All AI agents and contributors must observe these core research guardrails:
1. **Loopback Binding Only:** Web and API servers are bound strictly to `127.0.0.1`. No public exposure.
2. **Non-Destructive Simulated Remediation:** Entitlement revocations modify local database records only (`Revoked (Simulated)`). No destructive RPC/API calls are ever issued to remote target systems.
3. **Strict Human-in-the-Loop:** AI and ML anomaly outputs are purely advisory percentiles that prioritize human review queues. Automated revocation is strictly prohibited.
4. **Absence of Evidence is Not Evidence of Absence:** Missing telemetry or log events is treated as unverified evidence, never as definitive proof of dormancy or safe revocation.
