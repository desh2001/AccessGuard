# 🎬 AccessGuard — Video Presentation & Demo Script Guide
### (AI-Powered User Access Governance & Security Telemetry Ecosystem)

> **අරමුණ (Objective):**  
> මෙම ලේඛනය (Document) සකස් කර ඇත්තේ **AccessGuard** පද්ධතිය, **Dialog Access Log** සහ **Dialog Final ML** එකිනෙකට සම්බන්ධ වී ක්‍රියාත්මක වන ආකාරය පැහැදිලි කරමින් සම්පූර්ණ වීඩියෝවක් (Video Demo / Final Presentation) පටිගත කිරීමට සහ ඉදිරිපත් කිරීමට අවශ්‍ය සියලුම කරුණු, Scene-by-Scene Runbook එකක් සහ Sinhala/English Voiceover Script එකක් සමඟිනි.

---

## 📑 පටුන (Table of Contents)
1. [පද්ධතියේ ප්‍රධාන අරමුණ (Project Elevator Pitch)](#1-පද්ධතියේ-ප්‍රධාන-අරමුණ-project-elevator-pitch)
2. [සම්පූර්ණ Ecosystem Architecture එක](#2-සම්පූර්ණ-ecosystem-architecture-එක)
3. [සම්බන්ධ වී ඇති ප්‍රධාන කොටස් 3 (The 3 Connected Systems)](#3-සම්බන්ධ-වී-ඇති-ප්‍රධාන-කොටස්-3-the-3-connected-systems)
4. [Logs වලින් ML එකට දත්ත ගලා යන ආකාරය (Data Pipeline)](#4-logs-වලින්-ml-එකට-දත්ත-ගලා-යන-ආකාරය-data-pipeline)
5. [වීඩියෝව සඳහා Scene-by-Scene Script & Walkthrough](#5-වීඩියෝව-සඳහා-scene-by-scene-script--walkthrough)
6. [ඉදිරිපත් කිරීමේදී (Viva/Demo) අසන ප්‍රධාන ප්‍රශ්න සහ පිළිතුරු (Q&A)](#6-ඉදිරිපත්-කිරීමේදී-vivademo-අසන-ප්‍රධාන-ප්‍රශ්න-සහ-පිළිතුරු-qa)

---

## 1. පද්ධතියේ ප්‍රධාන අරමුණ (Project Elevator Pitch)

### ❓ අපි විසඳන ගැටලුව (The Enterprise Problem):
නූතන ආයතන වල සේවකයින් කාලයත් සමඟ විවිධ Systems (Active Directory, Linux Bastions, Cloud, GitHub) වලට සම්බන්ධ වෙද්දී ඔවුන්ට අනවශ්‍ය ලෙස Permissions එකතු වීම (**Access Creep**) සිදුවේ. 
- සේවකයින් අංශ මාරු වූ පසු හෝ අස්වූ පසුවත් පරණ Admin permissions ඉතිරිවීම (**Orphaned / Dormant Accounts**).
- කාර්යාලවල පවත්වන Periodic Access Reviews වලදී කළමනාකරුවන් කිසිදු සොයාබැලීමකින් තොරව සියල්ල Approve කිරීම (**Rubber-Stamping**).

### 🛡️ AccessGuard විසඳුම (The Solution):
**AccessGuard** යනු ආයතනයේ සත්‍ය Network Syslog Logs සහ සේවකයින්ගේ Identities එකිනෙකට ගලපා (**Correlate** කර), **Multi-Platform Machine Learning (Isolation Forest)** මඟින් අවදානම් සහගත Permissions හඳුනාගෙන, ආරක්ෂිතව **Simulated Remediation** කිරීමට ඉඩ සලසන මධ්‍යගත පාලන මධ්‍යස්ථානයකි (**Central Governance Hub**).

---

## 2. සම්පූර්ණ Ecosystem Architecture එක

පද්ධතිය එකිනෙකට සම්බන්ධ වන ආකාරය පෙන්වන සරල සටහන:

```text
┌─────────────────────────────────┐
│   Dialog Access Log (Pasindu)   │
│   - Syslog Listener (Port 5514) │
│   - Event Explorer (Port 8002)  │
└────────────────┬────────────────┘
                 │ 1. Raw Network Logs & Login Failures
                 ▼
┌──────────────────────────────────────────────────┐
│      AccessGuard Central Hub (Port 8000 & 5173)   │
│      - Canonical Identity Directory              │
│      - Account Mapping & Activity Correlation    │
│      - Access Reviews & Simulated Remediation    │
└────────────────┬─────────────────────────────────┘
                 │ 2. Entitlement Feature Payload (Inactivity, Privilege, Rule Score)
                 ▼
┌─────────────────────────────────┐
│    Dialog Final ML (Hashan)     │
│    - Port 8001 (/predict-risk)  │
│    - Windows AD Model (92.0%)   │
│    - Linux Host Model (94.9%)   │
│    - GitHub OAuth Model (96.9%) │
└─────────────────────────────────┘
```

---

## 3. සම්බන්ධ වී ඇති ප්‍රධාන කොටස් 3 (The 3 Connected Systems)

| Subsystem | Port / Protocol | කාර්යභාරය (Responsibility) |
|---|---|---|
| **AccessGuard Central Hub** | `Web UI :5173`<br>`FastAPI :8000`<br>`DB :5434` | මධ්‍යගත පාලන මධ්‍යස්ථානය. Identity Directory, Account Linking, Access Review Campaigns, සහ Simulated Remediation මෙහෙයවීම. |
| **Dialog Access Log** | `Syslog TCP :5514`<br>`API :8002` | Live Syslog Collector daemon. Network devices (VPNs, Domain Controllers, Linux Servers) වලින් සත්‍ය logs සහ login failure alerts ලබාගැනීම. |
| **Dialog Final ML** | `REST API :8001`<br>`/predict-risk` | Aegis V8 Multi-Platform Isolation Forest Engine. Windows, Linux, සහ GitHub යන models 3 හරහා Anomaly Percentiles ගණනය කිරීම. |

---

## 4. Logs වලින් ML එකට දත්ත ගලා යන ආකාරය (Data Pipeline)

වීඩියෝවේදී මේ කරුණ විශේෂයෙන් සඳහන් කළ යුතුය:

1. **Log Ingestion:** Network devices වලින් Port 5514 හරහා Syslog authentication events (Logins, Sudo, Failed passwords) ලබාගනී.
2. **Identity Correlation:** AccessGuard විසින් raw syslog packets වල ඇති `user_id` හෝ usernames, ආයතනයේ සත්‍ය Employee Account එක සමඟ match කරයි.
3. **Usage Timestamp Update:** අදාළ user ගේ Access Grant එකේ `last_verified_use` timestamp එක අලුත් වී `inactivity_days` ගණනය වේ.
4. **Feature Matrix Dispatch:** Backend එක මඟින් `[privilege, cross_dept, rule_score, inactivity_days]` අඩංගු payload එකක් HTTP POST මඟින් Port 8001 හි ML සේවාවට යවයි.
5. **ML Anomaly Scoring:** 
   - Log එකක් ලැබී සක්‍රීයව භාවිතාවන access වල Anomaly Score එක පහත වැටේ (Low Risk).
   - දින 90කට වැඩි කාලයක් කිසිදු Log එකක් නොමැති Dormant Access, Isolation Forest මඟින් **High Structural Anomaly** (85%+ Anomaly Percentile) ලෙස හඳුනාගෙන Urgent Human Review සඳහා Queue එකට දමයි.

---

## 5. වීඩියෝව සඳහා Scene-by-Scene Script & Walkthrough

---

### 🎬 Scene 1: Introduction & Master Launcher (0:00 - 1:00)
* **Screen එකේ පෙන්විය යුතු දේ:** `AccessGuard` folder එක. `start.bat` file එක double-click කර terminal windows 4ක් සහ Browser එකේ `http://127.0.0.1:5173` auto-open වන ආකාරය පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "ආයුබෝවන් හැමෝටම! අද මම ඔයාලට පෙන්නන්නේ Enterprise User Access Governance සහ Anomaly Detection සඳහා අපි නිර්මාණය කරපු **AccessGuard** පද්ධතියයි. 
  > මෙතනදී Dialog Access Log, Dialog Final ML කියන systems AccessGuard central dashboard එකට full integrate කරලා තියෙන්නේ. 
  > අපිට මේ සම්පූර්ණ ecosystem එකම එක click එකකින්, මෙන්න මේ `start.bat` file එකෙන් start කරන්න පුළුවන්. 
  > ඒකෙන් Docker Database එක, Core API එක, ML Microservice එක, සහ Syslog collector එක auto-start වෙලා Browser එකෙන් මේ විදියට Central Dashboard එක open වෙනවා."

---

### 🎬 Scene 2: Central Overview Dashboard (1:00 - 2:00)
* **Screen එකේ පෙන්විය යුතු දේ:** **Overview** tab එක. Total Identities, Active Accounts, Pending Reviews, සහ System Risk Distribution Charts mouse එකෙන් hover කර පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "මේ තියෙන්නේ AccessGuard Central Dashboard එක. මෙතනින් ආයතනයේ සේවකයින්ගේ Identities, systems හරහා link වෙලා තියෙන technical accounts, සහ සමස්ත අවදානම් තත්ත්වය (Risk Distribution) එක බැල්මෙන්ම බලාගන්න පුළුවන්. 
  > විශේෂයෙන්ම Active Directory, Linux Bastions, සහ GitHub කියන platforms තුනේම accounts සහ privileges මෙතන එකතු වෙනවා."

---

### 🎬 Scene 3: Account Mapping & Unlinked Accounts (2:00 - 3:00)
* **Screen එකේ පෙන්විය යුතු දේ:** **Linked Accounts** tab එක. Unlinked Technical Accounts (උදා: `svc-backup`, `dba_admin`) පෙන්වා, සේවකයෙකුට Link කරන ආකාරය පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "ආයතන වල තියෙන ලොකුම ප්‍රශ්නයක් තමයි අයිතිකාරයෙක් නැති Service Accounts සහ Orphaned Accounts. 
  > අපේ **Account Mapping** view එකෙන් unlinked technical accounts හඳුනාගෙන, ඒවා ආයතනයේ නියම සේවකයාට link කරන්න පුළුවන්. 
  > මෙහෙම link කරපු ගමන් ඒ පිළිබඳ සම්පූර්ණ විස්තරයක් Audit Log එකේ සටහන් වෙනවා."

---

### 🎬 Scene 4: Live Activity Evidence & Syslog Stream (3:00 - 4:30)
* **Screen එකේ පෙන්විය යුතු දේ:** **Activity Evidence** tab එක. 
  1. `Canonical Identity Evidence` sub-tab එක පෙන්වන්න.
  2. `Dialog Syslog Stream` sub-tab එකට මාරු වී port 5514 න් ලැබෙන live syslog logs පෙන්වන්න.
  3. **"Sync Syslog to Activity"** button එක click කර logs correlate වන ආකාරය පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "මේ තියෙන්නේ අපේ Activity Evidence tab එක. මෙතන විශේෂත්වයක් තියෙනවා:
  > Pasindu නිර්මාණය කරපු **Dialog Access Log** service එක TCP port 5514 හරහා ආයතනයේ live network devices වලින් syslog messages collect කරගන්නවා. 
  > ඔයාලට පේනවා ඇති `Dialog Syslog Stream` එකේ VPN logins, failed authentications, සහ sudo commands stream වෙන හැටි. 
  > මම මේ **'Sync Syslog to Activity'** button එක click කරපු ගමන්, ඒ raw logs වල ඉන්න users ලාව අපේ සේවකයින්ගේ Canonical Accounts වලට auto-match වෙලා database එකට correlate වෙනවා."

---

### 🎬 Scene 5: AI Risk Analysis & Platform ML Models (4:30 - 6:00)
* **Screen එකේ පෙන්විය යුතු දේ:** **AI Risk Analysis** tab එක. 
  1. **"Dialog Final ML (Live)"** badge එක පෙන්වන්න.
  2. ඉහළින් ඇති Aegis V8 Platform Models 3 (Windows 92.0%, Linux 94.9%, GitHub 96.9%) පෙන්වන්න.
  3. Rule Score vs ML Anomaly Percentile සන්සන්දනය පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "දැන් අපි යමු වඩාත්ම වැදගත් කොටස වන **AI Risk Analysis** එකට. 
  > මෙතනදී Hashan නිර්මාණය කරපු **Dialog Final ML Microservice** එක Port 8001 හරහා live connect වෙලා තියෙනවා. 
  > ඔයාලට පේනවා ඇති V8 Multi-Platform Models තුනම මෙතන load වෙලා තියෙනවා:
  > - Windows AD Model එක ROC-AUC 92% ක accurate අගයක් තියෙනවා.
  > - Linux Model එක 94.9% ක්.
  > - GitHub Model එක 96.9% ක්.
  > මෙතනදී පද්ධතිය Deterministic Rule Scores සහ Unsupervised ML Anomaly Percentiles එකට එකතු කරලා තමයි Anomaly එකක් තීරණය කරන්නේ. 
  > කලින් අපි sync කරපු logs වලින් user කෙනෙක් inactive ද, active ද කියන දත්තය ML model එකට pass වෙලා anomaly percentiles live ගණනය වෙනවා."

---

### 🎬 Scene 6: Access Reviews & Simulated Remediation (6:00 - 7:30)
* **Screen එකේ පෙන්විය යුතු දේ:** **Access Reviews** tab එක. 
  1. **"Generate risk-based reviews"** click කරන්න.
  2. Review queue එකේ තියෙන permission එකකට **"Approve removal"** දෙන්න.
  3. ඊළඟට **"Simulate revoke"** click කර local state එක වෙනස් වන හැටි පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "ML එකෙන් වැඩිපුර Anomaly තියෙන high-risk permissions හඳුනාගත්තට පස්සේ, අපි **Access Reviews** tab එකට යනවා. 
  > අපි මෙතනදී **Human-in-the-Loop** සංකල්පය ක්‍රියාත්මක කරලා තියෙනවා. ඒ කියන්නේ AI එකෙන් auto-delete කරන්නේ නෑ; Reviewer කෙනෙක් තීරණය කරන්න ඕනේ Retain කරනවද, Revoke කරනවද කියලා. 
  > Reviewer removal approve කළාට පස්සේ **'Simulate revoke'** මඟින් local database එකේ permission එක safe විදියට revoke වෙනවා. සජීවී servers වලට අනවශ්‍ය හානි නොවෙන විදියටයි මේ simulation එක නිර්මාණය කරලා තියෙන්නේ."

---

### 🎬 Scene 7: Offboarding Center & Integrations Hub (7:30 - 8:30)
* **Screen එකේ පෙන්විය යුතු දේ:** 
  1. **Offboarding** tab එක (Leavers with active access).
  2. **Integrations** tab එක (Dialog Access Log card, Dialog Final ML card, Ping buttons, Monitored Devices table).
* **Voiceover (Sinhala):**
  > "Offboarding tab එකෙන් ආයතනයෙන් අස්වෙලා ගියත් තාම permissions තියෙන සේවකයින් පෙන්වනවා. 
  > අවසාන වශයෙන් **Integrations** tab එකෙන් අපේ core architecture එක පේනවා. 
  > Dialog Access Log service එකේ live device metrics, failed logins, සහ Dialog Final ML service එකේ status එක මෙතනින් live monitor කරගන්න පුළුවන්."

---

### 🎬 Scene 8: Conclusion (8:30 - 9:00)
* **Screen එකේ පෙන්විය යුතු දේ:** **Audit Reports** හෝ **Research Reports** view එක. JSON/CSV export button එක පෙන්වන්න.
* **Voiceover (Sinhala):**
  > "සියලුම තීරණ සහ events මේ විදියට Audit Trail එකේ සටහන් වෙන අතර, ඕනෑම වෙලාවක Research Report එකක් CSV හෝ JSON විදියට export කරගන්න පුළුවන්. 
  > මේ විදියට AccessGuard මඟින් සම්පූර්ණ Identity Governance, Log Telemetry, සහ Machine Learning එකම වේදිකාවකට සාර්ථකව ගෙනවිත් තියෙනවා. බොහොම ස්තූතියි!"

---

## 6. ඉදිරිපත් කිරීමේදී (Viva/Demo) අසන ප්‍රධාන ප්‍රශ්න සහ පිළිතුරු (Q&A)

### Q1: Logs කොහොමද ML Model එකට සම්බන්ධ වෙන්නේ?
> **පිළිතුර:** Syslog messages (Port 5514 / Port 8002) Ingest වූ පසු, එමඟින් අදාළ identity ගේ `last_verified_use` timestamp එක update වේ. Backend එක මඟින් `inactivity_days`, `rule_score`, `privilege`, සහ `cross_department` යන features සකස් කර HTTP POST මඟින් ML microservice (`/predict-risk`) වෙත යවයි. Logs නොමැති dormant accounts වල Anomaly Percentile එක ඉහළ යයි.

### Q2: ML එකෙන් Permissions Auto-Revoke කරනවද?
> **පිළිතුර:** නැත. Enterprise Security වලදී AI මඟින් කෙලින්ම permissions revoke කිරීම අනතුරුදායකයි (False Positives නිසා critical services බිඳවැටිය හැක). එම නිසා අපේ පද්ධතිය **Human-in-the-Loop** ආකෘතිය භාවිතා කරයි. ML එකෙන් කරන්නේ Reviewers ලාට බලන්න ඕන ප්‍රමුඛතා පෝලිම (Prioritized Queue) සාදා දීම පමණි.

### Q3: V8 Platform Models වල ඇති වාසිය කුමක්ද?
> **පිළිතුර:** එක් generic model එකක් වෙනුවට Windows Active Directory, Linux Host, සහ GitHub යන platforms 3 සඳහාම වෙන වෙනම Train කරන ලද Isolation Forest models 3ක් භාවිතා කරයි. එමඟින් එක් එක් platform එකට ආවේණික හැසිරීම් (උදා: Sudo usage, AD Group nesting, Repo commit activity) නිවැරදිව හඳුනාගත හැක.
