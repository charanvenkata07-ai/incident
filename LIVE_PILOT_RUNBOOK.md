# INCIDENTFLOW — CONTROLLED LIVE PILOT RUNBOOK

**Document Version:** 1.0.0  
**Environment:** STAGING  
**Default Safety Mode:** `AUTOMATION_MODE=SHADOW`, `LIVE_PILOT_ENABLED=false`, `EMAIL_PROVIDER=MOCK`  
**Classification:** Restricted Operations / Production Readiness

---

## 1. Executive Summary & Purpose

This runbook defines the operational procedures for activating, monitoring, pausing, and rolling back a **controlled LIVE assignment pilot** in IncidentFlow. 

The LIVE pilot introduces live outbound assignment mutations to ServiceNow under strict, tamper-evident, fail-closed isolation guards. Under no circumstances should LIVE assignment be activated without adhering to every pre-condition and safety checklist step outlined in this document.

---

## 2. Pilot Safety Constraints & Guardrails

The IncidentFlow LIVE Pilot is engineered with defense-in-depth safeguards:

| Guardrail | Enforcement Mechanism | Failure / Violation Behavior |
| :--- | :--- | :--- |
| **Activation Safety** | Explicit `ADMIN` role + `confirmed=True` + exact confirmation phrase: `ENABLE LIVE ASSIGNMENT`. | Rejects request with HTTP 400; audit log records unauthorized or invalid attempt. |
| **Assignment Group Isolation** | Only incidents matching `LIVE_PILOT_ASSIGNMENT_GROUP` (`Analytics – MDM L3`) are automated. | Non-pilot incidents are ignored; state remains `NEW`; logged as `PILOT_GROUP_FILTERED`. |
| **Roster Isolation** | Only engineers explicitly listed in `LIVE_PILOT_ALLOWED_EMPLOYEES` can be assigned. | Non-roster engineers are excluded; if no roster engineer is eligible, escalates to `AUTO_ASSIGN_FAILED`. |
| **Eligibility Verification** | Normal eligibility requirements strictly enforced (active shift, presence check-in, availability `AVAILABLE`, skill matching). | Engineers on break, offline, or lacking required skills are bypassed. |
| **Capacity Ceiling Guard** | Active assignments capped at `LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS` (default: `5`). | Ingestion continues, but auto-assignment is throttled; logged as `PILOT_CAPACITY_REACHED`. |
| **Database Concurrency** | Row-level locking (`SELECT ... FOR UPDATE`) on Incident and Employee rows. | 10 concurrent requests result in exactly 1 successful assignment; 0 race conditions, 0 duplicate assignments. |
| **Mutation Sync Isolation** | Outbound ServiceNow mutation is isolated from local transaction. | If ServiceNow API fails, local assignment persists, incident marked `SYNC_FAILED`, and recorded in DLQ for retry. |
| **Zero Plaintext Credentials** | Secrets injected via environment variables; redacted from logs, responses, and UI. | Passwords and HMAC secrets are completely masked. |

---

## 3. Pre-Flight Checklist Before Pilot Activation

Before attempting to activate the LIVE pilot, an Administrator must verify all 14 readiness checks:

```bash
# Query live readiness report
curl -X GET http://localhost:8000/api/admin/live-pilot/readiness \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"
```

### Pre-Activation Verification Matrix:
- [ ] **ServiceNow Instance Reachability**: Real external instance resolves via TLS and responds.
- [ ] **ServiceNow Authentication**: Valid service account credentials return HTTP 200.
- [ ] **Incident Read Access**: Table API read access verified on `incident` table.
- [ ] **Synthetic Incident Verification**: 1 synthetic staging incident verified end-to-end.
- [ ] **Pilot Assignment Group**: Target group confirmed (e.g., `Analytics – MDM L3`).
- [ ] **Pilot Employee Roster**: Designated primary and secondary engineers confirmed.
- [ ] **In-App Notification & WebSocket**: Verified working on `/my-work` and `/notifications`.
- [ ] **Audit Logging Active**: Verified in PostgreSQL `audit_logs` table.
- [ ] **Dead Letter Queue Operational**: Verified via `/api/admin/integrations/failures`.
- [ ] **Emergency Pause Verified**: Operators trained on one-click pause.
- [ ] **Rollback Procedure Verified**: Operators trained on instant revert to `SHADOW`.

> [!CAUTION]
> If `ready_for_live == False`, DO NOT attempt to force LIVE mode. Resolve all blockers first.

---

## 4. Activation Procedure

### Option A: Via Admin Control Center (Recommended)
1. Log in to IncidentFlow as an `ADMIN` user (`admin@incidentflow.dev`).
2. Navigate to **Admin** $\rightarrow$ **Live Pilot** (`/admin/live-pilot`).
3. Verify the **Pre-Live Readiness & Safety Checklist** card.
4. Review the **Pilot Isolation Parameters** (Assignment Group, Max Active, Allowed Roster).
5. Click **Activate LIVE Pilot**.
6. In the safety modal, enter the exact phrase:
   ```
   ENABLE LIVE ASSIGNMENT
   ```
7. Click **Confirm & Enable LIVE Assignment**.
8. Verify that the status badge changes to **● LIVE PILOT ACTIVE** (Emerald).

### Option B: Via Command Line / API
```bash
curl -X POST http://localhost:8000/api/admin/automation/mode \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: $(uuidgen)" \
  -d '{
    "mode": "LIVE",
    "confirmed": true,
    "confirmation_phrase": "ENABLE LIVE ASSIGNMENT"
  }'
```

---

## 5. Live Monitoring & Telemetry

During active pilot operation, monitor the following surfaces:

### 1. Admin Live Pilot Dashboard (`/admin/live-pilot`)
- **Active Pilot Assignments**: Current count vs max allowed ceiling.
- **Assigned Today**: Cumulative count of pilot assignments.
- **ServiceNow Syncs vs Failures**: Outbound mutation success rate.
- **Dead Letter Queue**: Should remain 0.

### 2. Tail Application Logs
```bash
# Filter for pilot decision events
docker logs -f incidentflow-backend | grep -E "pilot_group_filtered|LIVE_ASSIGNMENT|PILOT_CAPACITY_REACHED|servicenow_sync"
```

### 3. Verify Employee In-App View
- Log in as the assigned pilot engineer (e.g. `ravi@incidentflow.dev`).
- Verify ticket appears under **My Work** (`/my-work`).
- Verify in-app bell notification was delivered.

---

## 6. Emergency Procedures

### Immediate Emergency Pause
If any anomalous behavior is detected, trigger Emergency Pause immediately:

**UI Action:**
Click the **Emergency Pause** button on `/admin/live-pilot` or `/admin/integrations`.

**API Action:**
```bash
curl -X POST http://localhost:8000/api/admin/automation/pause \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>"
```

**Result of Emergency Pause:**
- Automated assignments halt immediately.
- Incoming ServiceNow webhooks are still received and persisted as `NEW`.
- Existing assignments and engineer work-in-progress are preserved.
- Audit event `AUTOMATION_STATUS_CHANGED` is logged with actor ID and timestamp.

---

## 7. Escalation Contacts

| Role | Contact | Responsibility |
| :--- | :--- | :--- |
| **Lead SRE / Platform Admin** | admin@incidentflow.dev | Pilot execution and emergency controls |
| **IncidentFlow On-Call** | oncall@incidentflow.dev | Application engine and database triage |
| **ServiceNow Integration Lead** | sn-admin@company.internal | ServiceNow instance health & credentials |
