# 🛡️ AccessGuard: Comprehensive Architecture Blueprint & Video Presentation Guide

> **Authoritative Technical Reference & Video Recording Runbook**  
> **Project:** AccessGuard Unified User Access Governance & Anomaly Detection Ecosystem  
> **Components:** AccessGuard Central Hub, Dialog Access Log (Syslog), Dialog Final ML (Aegis V8)

---

## Table of Contents
1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [End-to-End System Architecture](#2-end-to-end-system-architecture)
3. [Deep-Dive Component Specifications](#3-deep-dive-component-specifications)
   - [A. AccessGuard Central Governance Hub](#a-accessguard-central-governance-hub)
   - [B. Dialog Access Log Telemetry Pipeline](#b-dialog-access-log-telemetry-pipeline)
   - [C. Dialog Final ML Microservice (Aegis V8)](#c-dialog-final-ml-microservice-aegis-v8)
4. [Data Flow Pipeline & Sequence Mechanics](#4-data-flow-pipeline--sequence-mechanics)
5. [Feature Engineering & Anomaly Scoring Mathematics](#5-feature-engineering--anomaly-scoring-mathematics)
6. [Security Guardrails & Human-in-the-Loop Philosophy](#6-security-guardrails--human-in-the-loop-philosophy)
7. [Full Video Recording Script & Director's Runbook](#7-full-video-recording-script--directors-runbook)
   - [Scene 1: Introduction & One-Click Master Launcher](#scene-1-introduction--one-click-master-launcher-000---050)
   - [Scene 2: Central Overview & Telemetry Posture](#scene-2-central-overview--telemetry-posture-050---145)
   - [Scene 3: Account Mapping & Unlinked Technical Accounts](#scene-3-account-mapping--unlinked-technical-accounts-145---240)
   - [Scene 4: Live Syslog Telemetry & Correlation Pipeline](#scene-4-live-syslog-telemetry--correlation-pipeline-240---350)
   - [Scene 5: AI Risk Analysis & V8 Multi-Platform Isolation Forests](#scene-5-ai-risk-analysis--v8-multi-platform-isolation-forests-350---515)
   - [Scene 6: Human-in-the-Loop Access Reviews & Simulated Remediation](#scene-6-human-in-the-loop-access-reviews--simulated-remediation-515---630)
   - [Scene 7: Offboarding Center & Leaver Governance](#scene-7-offboarding-center--leaver-governance-630---720)
   - [Scene 8: Central Integrations & Diagnostic Hub](#scene-8-central-integrations--diagnostic-hub-720---810)
   - [Scene 9: Audit Trail, Reporting & Closing Conclusion](#scene-9-audit-trail-reporting--closing-conclusion-810---900)
8. [Technical Evaluation Defense & Examiner Q&A](#8-technical-evaluation-defense--examiner-qa)

---

## 1. Executive Summary & Problem Statement

### The Enterprise Challenge: "Access Creep" and Dormant Privileges
In modern enterprise infrastructures spanning Active Directory, Linux production clusters, Cloud environments, and GitHub organizations, managing identity privileges is one of the most failure-prone security functions:
1. **Access Creep & Privilege Accumulation:** Employees transition across roles and departments, accumulating administrative permissions without historical entitlements ever being revoked.
2. **Orphaned & Technical Accounts:** Machine accounts, automated scripts, and external contractors hold elevated credentials without documented human ownership.
3. **The Rubber-Stamping Dilemma:** Periodic identity access reviews frequently devolve into arbitrary approval exercises because line managers lack granular, activity-based evidence to justify revoking access.
4. **Dangerous Autonomous Remediation:** Commercial solutions that attempt fully automated permission revocation risk taking down critical production workloads due to false-positive anomaly classifications.

### The AccessGuard Solution
**AccessGuard** is a local-first, multi-component Identity Governance and Administration (IGA) and User Access Governance (UAG) research platform. It connects live network authentication telemetry (Syslog over TCP `5514`), normalizes and correlates activity to canonical employee profiles, uses platform-specific machine learning models (Isolation Forests) to score structural anomalies, and provides human reviewers with an explainable review-and-remediation workflow.

---

## 2. End-to-End System Architecture

```text
                                 ┌──────────────────────────────────────────────────┐
                                 │               Client Web Browser                 │
                                 │         http://127.0.0.1:5173 (React UI)         │
                                 └────────────────────────┬─────────────────────────┘
                                                          │ HTTP / Reverse Proxy
                                                          ▼
┌─────────────────────────────────┐              ┌──────────────────────────────────┐
│  Dialog Access Log (Pasindu)    │              │  AccessGuard Core Backend        │
│  - TCP Syslog Ingestion (:5514) │ REST API     │  - FastAPI REST Service (:8000)  │
│  - Event Ingestion API (:8002)  ├─────────────►│  - Identity & Account Mapping    │
│  - Monitored Devices Registry   │ Sync Trigger │  - Activity Correlation Engine   │
└─────────────────────────────────┘              │  - Review Campaign Manager       │
                                                 └────────┬──────────────────┬──────┘
                                                          │                  │
                         SQLAlchemy 2.0 (Host Port 5434)  │                  │ HTTP POST /predict-risk
                                                          ▼                  ▼ (Port 8001)
                                                 ┌─────────────────┐ ┌──────────────────────────────┐
                                                 │ PostgreSQL 17   │ │ Dialog Final ML     │
                                                 │ (Docker Compose)│ │ - Multi-Platform Isolation   │
                                                 │ accessguard_lab │ │   Forest (Win, Linux, GitHub)│
                                                 └─────────────────┘ └──────────────────────────────┘
```

---

## 3. Deep-Dive Component Specifications

### A. AccessGuard Central Governance Hub
* **Frontend:** React 19, Tailwind CSS v4, Lucide Icons, Recharts data visualization.
* **Backend:** FastAPI, Python 3.11+, SQLAlchemy 2.0 ORM, Alembic schema migrations.
* **Persistence:** PostgreSQL 17 running inside Docker, exposed on host port `5434` (mapped to container port `5432` to avoid host port collisions).
* **Core Responsibilities:**
  - Maintains the **Canonical Identity Directory** (human employees, job titles, departments, operational status).
  - Resolves cross-platform technical accounts (`WIN`, `LIN`, `GH`, `AWS`) and flags orphaned credentials.
  - Computes explainable deterministic baseline risk scores based on privilege, department boundaries, and verified usage.
  - Dispatches normalized feature vectors to the ML engine and presents prioritized review queues.

### B. Dialog Access Log Telemetry Pipeline
* **Syslog Receiver:** Multi-threaded TCP stream socket daemon listening on `0.0.0.0:5514`.
* **Telemetry API:** FastAPI service running on port `8002` (`standalone_api.py`).
* **Ingestion Logic:**
  - Ingests raw RFC-compliant syslog datagrams from VPN gateways, Windows Domain Controllers (Event 4624/4625), and Linux Bastion hosts (`sshd`, `sudo`).
  - Evaluates message semantics using heuristic classifiers (`LOGIN_SUCCESS`, `LOGIN_FAILED`, `PRIVILEGE_USED`, `LOGOUT`).
  - Tracks monitored device health, IP addressing, and failed login bursts.

### C. Dialog Final ML Microservice (Aegis V8)
* **Inference Endpoint:** FastAPI microservice running on `127.0.0.1:8001` (`mock_ml_service.py`).
* **Multi-Platform Model Architecture:** Rather than using a single, diluted generic model, Aegis V8 incorporates three independent Isolation Forest models trained on platform-specific feature spaces:
  - **Windows Active Directory Model:** 160 estimators, 32 dimensional features, **ROC-AUC: 92.01%**, Average Precision: 68.22%.
  - **Linux PAM Host Model:** 160 estimators, 26 dimensional features, **ROC-AUC: 94.91%**, Average Precision: 80.36%.
  - **GitHub OAuth Model:** 160 estimators, 25 dimensional features, **ROC-AUC: 96.91%**, Average Precision: 90.39%.
* **Output Metrics:** Computes relative anomaly percentiles ($0\% - 100\%$) and blends them into an actionable **Combined Priority Score**.

---

## 4. Data Flow Pipeline & Sequence Mechanics

The lifecycle of an authentication log turning into an AI risk score follows five strictly sequenced stages:

```text
[Network Device]
      │ (1. Raw Syslog Packet: "sshd[19284]: Failed password for invalid user hashan.h from 10.77.0.1")
      ▼
[Dialog Access Log Listener :5514]
      │ (2. Categorization -> Event Type: LOGIN_FAILED, Severity: Warning)
      ▼
[Dialog Access Log API :8002]
      │ (3. HTTP GET /api/events via AccessGuard Sync Trigger)
      ▼
[AccessGuard Correlation Engine :8000]
      │ (4. Username Extraction -> Match 'hashan.h' to Canonical Identity)
      │ (5. Update Account.last_seen_at & AccessGrant.last_verified_use)
      │ (6. Inactivity Evaluation -> Calculate days_since_last_verified_use)
      ▼
[Feature Extraction & Payload Assembly]
      │ (7. HTTP POST /predict-risk -> [grant_id, privilege, cross_dept, rule_score, system_id])
      ▼
[Dialog Final ML Service :8001]
      │ (8. Isolation Forest Feature Projection & Decision Path Evaluation)
      │ (9. Anomaly Score Ranking -> Anomaly Percentile Computation)
      ▼
[AccessGuard Review Queue :5173]
        (10. Human Decision: Retain vs. Approve Revocation -> Simulated Execution)
```

---

## 5. Feature Engineering & Anomaly Scoring Mathematics

### Deterministic Rule-Based Risk Formula
The baseline risk score ($S_{\text{rule}} \in [10, 100]$) is additive and deterministic:
$$S_{\text{rule}} = \min\left(100, \; 10 + W_{\text{orphan}} + W_{\text{departed}} + W_{\text{admin}} + W_{\text{cross\_dept}} + W_{\text{inactivity}}\right)$$

Where the standard operational weights are defined as:
* $W_{\text{orphan}} = 40$: Technical account not linked to any verified employee.
* $W_{\text{departed}} = 50$: Terminated employee still retaining active system access.
* $W_{\text{admin}} = 23$: High-privilege administrative permission (`sudo`, `Domain Admins`, `Owner`).
* $W_{\text{cross\_dept}} = 23$: Account department does not match target resource department.
* $W_{\text{inactivity}} = 23$ (if $\ge 90$ days inactive) or $9$ (if $45 - 89$ days inactive).

### Machine Learning Anomaly Score & Combined Priority
The Isolation Forest measures how few splits are required to isolate an entitlement point $x$ in feature space:
$$s(x, n) = 2^{-\frac{\mathbb{E}(h(x))}{c(n)}}$$
Where $\mathbb{E}(h(x))$ is the average path length across 160 decision trees, and $c(n)$ is the average path length of unsuccessful searches in a Binary Search Tree.

The anomaly percentile ($P_{\text{anomaly}} \in [0, 100]$) is computed by ordering batch anomaly decision values. The **Combined Priority Score** ($C$) presented to reviewers is:
$$C = \text{round}\left(0.65 \times S_{\text{rule}} + 0.35 \times P_{\text{anomaly}}\right)$$

* **Combined Priority $\ge 85$:** **Critical Risk** $\rightarrow$ Escalated for Urgent Review.
* **Combined Priority $60 - 84$:** **High Risk** $\rightarrow$ Flagged for Human Review.
* **Combined Priority $< 60$:** **Standard Baseline** $\rightarrow$ Continuous Monitoring.

---

## 6. Security Guardrails & Human-in-the-Loop Philosophy

AccessGuard operates under strict research and enterprise ethical guardrails:
1. **Zero Uncontrolled Revocation:** Machine learning models are strictly advisory. No model output can directly invoke external APIs or issue destructive revoke commands.
2. **Absence of Evidence is Not Evidence of Absence:** Missing activity logs are never treated as definitive proof of dormancy unless corroborated by verified log source coverage.
3. **Simulated Remediation:** Remediation actions transition records into a local `Revoked (Simulated)` status, enabling compliance testing without risking production uptime.

---

## 7. Full Video Recording Script & Director's Runbook

---

### Scene 1: Introduction & One-Click Master Launcher (0:00 - 0:50)
* **Visual Focus:** The project root folder in Windows File Explorer.
* **On-Screen Action:** 
  1. Hover cursor over `start.bat`.
  2. Double-click `start.bat`.
  3. Show the four automated PowerShell windows initializing: PostgreSQL (:5434), Core Backend (:8000), Dialog ML (:8001), and Dialog Access Log (:8002).
  4. Watch the browser automatically launch `http://127.0.0.1:5173`.
* **Voiceover Narration:**
  > "Welcome to the demonstration of AccessGuard, an intelligent User Access Governance and Anomaly Detection ecosystem. 
  > In enterprise environments, tracking who has access to what, identifying dormant accounts, and detecting access anomalies across multiple platforms is a critical challenge. 
  > AccessGuard integrates real-time network syslog telemetry and multi-platform machine learning into a unified governance dashboard. 
  > To run our complete suite, we built a zero-friction master launcher. With a single double-click on `start.bat`, our script spins up our PostgreSQL container, initializes database migrations, starts our Dialog ML engine, launches our Syslog collector daemon, and brings up our React central dashboard—opening automatically in the browser."

---

### Scene 2: Central Overview & Telemetry Posture (0:50 - 1:45)
* **Visual Focus:** The **Overview** tab of the React Dashboard.
* **On-Screen Action:**
  1. Pan across the top metric cards (Identities, Mapped Accounts, Active Grants, Pending Reviews).
  2. Hover over the System Inventory cards (Active Directory, Linux Clusters, GitHub Org).
  3. Hover over the Entitlement Risk Distribution bar and pie charts.
* **Voiceover Narration:**
  > "This is the AccessGuard Central Governance Dashboard. Here, security officers get an immediate, comprehensive overview of the organization's identity posture. 
  > We can inspect our canonical human employees, cross-system technical accounts, and the distribution of permissions across platforms. 
  > Rather than treating systems in silos, AccessGuard normalizes access rights across Active Directory, Linux servers, and GitHub organizations into a single unified inventory, tracking critical and high-risk permissions in real time."

---

### Scene 3: Account Mapping & Unlinked Technical Accounts (1:45 - 2:40)
* **Visual Focus:** Navigate to the **Linked Accounts** tab.
* **On-Screen Action:**
  1. Point out the Unlinked Technical Accounts table (`svc-backup`, `dba_admin`).
  2. Select an unlinked account, click **Link to Employee**, choose an employee from the dropdown, and submit.
  3. Show the toast notification and demonstrate that the account status immediately updates to 'Linked'.
* **Voiceover Narration:**
  > "A major vulnerability in enterprise security is orphaned or unlinked technical accounts—accounts created for maintenance or scripts that lack a documented human owner. 
  > In our Account Mapping center, AccessGuard isolates these unlinked accounts. 
  > Security administrators can review ownership evidence and link technical accounts directly to canonical employee identities. 
  > Once linked, all permissions held by that account are attributed to that employee, and an immutable record is logged in the audit trail."

---

### Scene 4: Live Syslog Telemetry & Correlation Pipeline (2:40 - 3:50)
* **Visual Focus:** Navigate to the **Activity Evidence** tab.
* **On-Screen Action:**
  1. Show the `Canonical Identity Evidence` sub-tab with correlated timestamps.
  2. Click the `Dialog Syslog Stream` sub-tab.
  3. Highlight live events arriving from port `5514`: VPN gateway connections, Windows 4624/4625 authentications, and Linux sudo commands.
  4. Click the **"Sync Syslog to Activity"** button and observe the success notification.
* **Voiceover Narration:**
  > "Now, let's explore our live telemetry pipeline. In the Activity Evidence tab, we integrate directly with Pasindu's Dialog Access Log service. 
  > The collector daemon listens on TCP port 5514, receiving real-time syslog streams from network devices like VPN gateways and domain controllers. 
  > Under the 'Dialog Syslog Stream' tab, we can inspect real-time login successes, privilege escalation attempts, and login failures. 
  > When we click 'Sync Syslog to Activity', AccessGuard parses usernames out of the raw syslog packets, matches them to our canonical employee accounts, and automatically refreshes their last-verified-usage timestamps in our central database."

---

### Scene 5: AI Risk Analysis & V8 Multi-Platform Isolation Forests (3:50 - 5:15)
* **Visual Focus:** Navigate to the **AI Risk Analysis** tab.
* **On-Screen Action:**
  1. Point out the **"Dialog Final ML (Live)"** badge at the top right of the ML panel.
  2. Emphasize the three Aegis V8 Platform Model cards (Windows AD, Linux Host, GitHub OAuth) showing their tree counts and ROC-AUC scores.
  3. Show the comparison table: Rule Score vs. Anomaly Percentile vs. Combined Priority.
* **Voiceover Narration:**
  > "This brings us to our AI Risk Analysis engine, which connects directly to Hashan's Dialog Final ML microservice running on port 8001. 
  > AccessGuard features the Aegis V8 Multi-Platform Isolation Forest architecture. Rather than relying on a single generic model, we utilize three independent, platform-specific models:
  > - Our Windows Active Directory model achieves a 92% ROC-AUC score.
  > - Our Linux Host PAM model achieves 94.9%.
  > - Our GitHub OAuth model achieves 96.9%.
  > When our sync pipeline updates an employee's activity logs, fresh usage lowers dormancy anomalies. 
  > Conversely, if an account holds high-privilege access with no recorded activity for over 90 days, the Isolation Forest isolates that feature vector with very short path lengths, assigning it an anomaly percentile above 85% and escalating it for urgent review."

---

### Scene 6: Human-in-the-Loop Access Reviews & Simulated Remediation (5:15 - 6:30)
* **Visual Focus:** Navigate to the **Access Reviews** tab.
* **On-Screen Action:**
  1. Click **"Generate risk-based reviews"** to populate the campaign.
  2. Inspect an urgent ticket: show the user, system, privilege flag, and ML anomaly explanation.
  3. Click **"Approve removal"** on a high-risk ticket.
  4. Click **"Simulate revoke"** and show the status change to `Revoked (Simulated)`.
* **Voiceover Narration:**
  > "With high-risk anomalies identified, we move into the Access Reviews workflow. 
  > We strictly uphold a Human-in-the-Loop security philosophy. AI models should never autonomously revoke access without human confirmation. 
  > When we click 'Generate risk-based reviews', AccessGuard queues elevated risks for reviewer inspection. 
  > The reviewer sees explainable evidence: the deterministic policy score alongside the ML anomaly percentile. 
  > If the reviewer decides the permission is no longer justified, they click 'Approve removal'. 
  > Then, running 'Simulate revoke' executes a safe local remediation, updating our state without risking accidental downtime on production infrastructure."

---

### Scene 7: Offboarding Center & Leaver Governance (6:30 - 7:20)
* **Visual Focus:** Navigate to the **Offboarding** tab.
* **On-Screen Action:**
  1. Review departed employees who still hold active permissions across corporate systems.
  2. Highlight the recommendation badges ('Review required').
* **Voiceover Narration:**
  > "Our Offboarding Center tackles another classic identity attack vector: departed employees who still retain access across legacy systems. 
  > AccessGuard correlates HR departure statuses with active account grants. 
  > Any departing employee holding active accounts is flagged for immediate review, preventing orphaned access from persisting after employee offboarding."

---

### Scene 8: Central Integrations & Diagnostic Hub (7:20 - 8:10)
* **Visual Focus:** Navigate to the **Integrations** tab.
* **On-Screen Action:**
  1. Showcase the **Dialog Access Log Service** card: show port 5514, API port 8002, and click **"Ping API"**.
  2. Showcase the **Dialog Final ML Service** card: show port 8001, algorithm details, and click **"Ping ML Service"**.
  3. Scroll down to show the Monitored Devices registry and active anomaly alerts.
* **Voiceover Narration:**
  > "In the Integrations Hub, we can monitor the health of our distributed components. 
  > We see live telemetry from the Dialog Access Log daemon, tracking connected devices and failed login bursts. 
  > We can ping the Dialog Final ML microservice to verify real-time REST inference connectivity. 
  > This hub confirms that our telemetry collector, our machine learning engine, and our central governance database are operating in perfect synchronization."

---

### Scene 9: Audit Trail, Reporting & Closing Conclusion (8:10 - 9:00)
* **Visual Focus:** Navigate to **Audit Reports** and **Research Reports**.
* **On-Screen Action:**
  1. Scroll through the chronological audit log showing all linking, review, and sync actions.
  2. Click **"Download research report (JSON)"** to demonstrate reporting capabilities.
* **Voiceover Narration:**
  > "Every decision, account linkage, and simulated revocation is recorded in our chronological Audit Trail. 
  > Security officers and research evaluators can export comprehensive governance summaries directly to JSON or CSV for compliance auditing. 
  > In conclusion, AccessGuard demonstrates how enterprise identity governance, live syslog telemetry, and explainable multi-platform machine learning can work together seamlessly to eliminate access creep while keeping human decision-makers firmly in control. 
  > Thank you for watching!"

---

## 8. Technical Evaluation Defense & Examiner Q&A

### Q1: How do logs collected via the API actually feed into the Machine Learning model?
> **Answer:** When syslog messages arrive over TCP `5514` or through the AccessLog API (`:8002`), AccessGuard extracts the username, maps it to a canonical employee account, and updates the `last_verified_use` timestamp of associated access grants. When evaluating risk, AccessGuard computes features including `inactivity_days`, `rule_score`, `privilege`, and `cross_department`, packaging them into an HTTP POST payload sent to the ML service (`/predict-risk` on port `8001`). The Isolation Forest evaluates this normalized feature vector; accounts with active log evidence receive low anomaly percentiles, while dormant, unlogged accounts receive elevated anomaly percentiles above 85%.

### Q2: Why use three separate platform Isolation Forests instead of one large model?
> **Answer:** Feature representations across platforms are heterogeneous. Windows Active Directory involves Kerberos ticket exchanges, Group nesting, and Event 4624 logon types; Linux environments focus on PAM, SSH public keys, and sudo executions; GitHub relies on repository permissions and OAuth tokens. Training a single model creates feature dilution. By segmenting into Windows, Linux, and GitHub models, Aegis V8 achieves significantly higher discriminatory accuracy, yielding ROC-AUC scores of 92.0%, 94.9%, and 96.9% respectively.

### Q3: Why doesn't AccessGuard automatically revoke permissions using AI?
> **Answer:** Fully autonomous revocation in enterprise security introduces critical operational risk. A false positive could revoke database access for an incident responder during an active outage. AccessGuard adheres to the **Human-in-the-Loop (HITL)** paradigm: AI anomaly detection serves to triage and prioritize review queues, while human managers review the evidence and authorize decisions. Furthermore, remediation in this prototype is safely simulated locally to eliminate the risk of accidental production impact.
