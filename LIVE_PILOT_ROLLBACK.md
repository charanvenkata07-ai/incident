# INCIDENTFLOW — CONTROLLED LIVE PILOT ROLLBACK PROCEDURE

**Document Version:** 1.0.0  
**Target Environment:** STAGING / CONTROLLED LIVE PILOT  
**Primary Goal:** Deterministic, instantaneous reversion of live pilot operations without data loss.

---

## 1. Rollback Triggers & Decision Thresholds

Initiate a rollback immediately if any of the following conditions occur:

| Condition | Threshold | Action |
| :--- | :--- | :--- |
| **ServiceNow Mutation Errors** | > 2 consecutive sync failures or DLQ transitions | Level 1: Emergency Pause |
| **Assignment Group Spillover** | Any assignment attempt outside `LIVE_PILOT_ASSIGNMENT_GROUP` | Level 2: Immediate Revert to SHADOW |
| **Roster Spillover** | Any assignment made to an engineer not in `LIVE_PILOT_ALLOWED_EMPLOYEES` | Level 2: Immediate Revert to SHADOW |
| **Excessive Assignment Volume** | Active assignments exceed `LIVE_PILOT_MAX_ACTIVE_ASSIGNMENTS` | Level 1: Emergency Pause |
| **High API Latency** | ServiceNow round-trip latency > 5000ms | Level 1: Emergency Pause |
| **Administrator Directive** | Human operator issues stop command | Level 2: Immediate Revert to SHADOW |

---

## 2. Multi-Level Rollback Execution

### Level 1: Emergency Pause (Rapid Freeze)
*Halts all new automated assignments immediately. Incoming webhooks continue to ingest tickets safely in state `NEW`.*

#### Method A: Via Web UI
1. Navigate to `/admin/live-pilot` or `/admin/integrations`.
2. Click the red **Emergency Pause** button.
3. Status badge updates immediately to **● AUTOMATION PAUSED**.

#### Method B: Via CLI / API
```bash
curl -X POST http://localhost:8000/api/admin/automation/pause \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "X-Request-ID: $(uuidgen)"
```

---

### Level 2: Immediate Revert to SHADOW (Full Rollback)
*Transitions the assignment engine back to SHADOW mode. The engine continues to evaluate candidate dossiers and log decisions, but all outbound ServiceNow assignment mutations are strictly prohibited.*

#### Method A: Via Web UI
1. Navigate to `/admin/live-pilot`.
2. Click **Revert to SHADOW**.
3. Confirm prompt. Status transitions to **○ PILOT OFF (SHADOW MODE)**.

#### Method B: Via CLI / API
```bash
curl -X POST http://localhost:8000/api/admin/automation/mode \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: $(uuidgen)" \
  -d '{
    "mode": "SHADOW"
  }'
```

---

### Level 3: Revert to DRY RUN (Read-Only Recommendation Mode)
*Disables both assignment creation and outbound mutations. Candidate recommendations are logged to audit logs for manual inspection only.*

```bash
curl -X POST http://localhost:8000/api/admin/automation/mode \
  -H "Authorization: Bearer <ADMIN_JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: $(uuidgen)" \
  -d '{
    "mode": "DRY_RUN"
  }'
```

---

## 3. Data Integrity & Verification Steps

Following any rollback execution, verify the following four safety guarantees:

### 1. Zero Record Deletion
Verify that all incidents, assignments, and audit logs created during the pilot remain intact in PostgreSQL:
```sql
SELECT count(*) FROM incidents;
SELECT count(*) FROM incident_assignments;
SELECT count(*) FROM audit_logs WHERE action IN ('LIVE_ASSIGNMENT', 'CHANGE_AUTOMATION_MODE');
```

### 2. Audit Trail Confirmation
Verify that the rollback event was captured with actor identity and timestamp:
```sql
SELECT created_at, actor_id, action, old_value, new_value, reason 
FROM audit_logs 
WHERE action = 'CHANGE_AUTOMATION_MODE' 
ORDER BY created_at DESC LIMIT 5;
```

### 3. ServiceNow Mutation Verification
Confirm that no outbound HTTP requests to ServiceNow table endpoints are dispatched while in SHADOW mode:
```bash
docker logs incidentflow-backend | grep "servicenow_client_mutation_prohibited_in_shadow_mode"
```

### 4. Active Assignment Status
Incidents that were assigned prior to the rollback remain in their current state (`ASSIGNED` or `IN_PROGRESS`) so assigned engineers can continue resolving their active tickets without disruption.

---

## 4. Post-Rollback Incident Resolution

1. Open the Dead Letter Queue in `/admin/integrations` to review any failed sync payloads.
2. For any ticket requiring manual reassignment, use `/admin/assignments` or the ServiceNow UI directly.
3. Convene an operational review meeting before attempting any future LIVE pilot reactivation.
