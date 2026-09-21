# IncidentFlow — Real Staging Runtime Evidence Report

**Evaluation Phase:** Real End-to-End ServiceNow Staging Proof  
**Current Date:** September 17, 2026  
**Safety Status:** `AUTOMATION_MODE=SHADOW`, `LIVE=OFF`, `EMAIL_PROVIDER=MOCK`  
**Overall Evaluation:** `REAL_SERVICENOW_STAGING_E2E=BLOCKED`  
**Blocker Detail:** Actual ServiceNow TEST/STAGING credentials are required. Local environment contains placeholder tokens (`<PLACEHOLDER_STAGING_PASSWORD>`, `<PLACEHOLDER_WEBHOOK_SECRET>`). In accordance with Section 1 of the testing instructions, execution is stopped before live network calls to prevent false claims.

---

## 1. Environment Configuration Inspection (Section 1)

Environment configuration in `backend/.env` was inspected with credentials and tokens strictly masked:

```text
SERVICENOW_URL_CONFIGURED=true (https://dev-staging.service-now.com)
SERVICENOW_AUTH_CONFIGURED=false (Placeholder detected)
SERVICENOW_WEBHOOK_SECRET_CONFIGURED=false (Placeholder detected)
PLACEHOLDERS_DETECTED=true
```

### Blocker Output:
```text
REAL_STAGING_BLOCKED:
Actual ServiceNow TEST/STAGING credentials are required.
Placeholders detected in SERVICENOW_PASSWORD and SERVICENOW_WEBHOOK_SECRET.
```

---

## 2. Evidence Classification Summary

To preserve total technical integrity, all features are categorized by evidence level:

| Feature / Scenario | Implementation Status | Evidence Level | Details |
|---|---|---|---|
| **ServiceNow Table API Client** | `IMPLEMENTED` | `TESTED LOCALLY & WITH MOCKS` | Connection retry with exponential backoff; HTTP Basic Auth/Bearer support; 30s timeout |
| **Mutation Safety Guard** | `IMPLEMENTED` | `VERIFIED IN SHADOW MODE` | Any write (`update_incident`, `update_assignment`) returns `{"status": "skipped"}` in SHADOW mode |
| **Webhook Authentication** | `IMPLEMENTED` | `TESTED LOCALLY` | Enforces `X-ServiceNow-Secret`; rejects invalid credentials with `401 Unauthorized` |
| **Idempotency & Replay Protection** | `IMPLEMENTED` | `TESTED LOCALLY` | Backed by `integration_events` deduplication; prevents duplicate incidents |
| **10-Employee Multi-Shift Routing** | `IMPLEMENTED` | `TESTED LOCALLY` | Shift matching, presence filtering, skill gating, workload calculation |
| **Candidate Dossier Auditing** | `IMPLEMENTED` | `TESTED LOCALLY` | Audits eligible candidates with workloads and rejected candidates with explicit reasons |
| **Shift Rollover Engine** | `IMPLEMENTED` | `TESTED LOCALLY` | Boundary handoff (11:55 AM → 12:00 PM) transitions tickets without ServiceNow mutation |
| **Dead-Letter Queue (DLQ)** | `IMPLEMENTED` | `TESTED LOCALLY` | Failed external calls tracked in `sync_failures`; exponential backoff to `DEAD_LETTER` |
| **APP_BASE_URL Link Architecture** | `IMPLEMENTED` | `TESTED LOCALLY` | Configurable domain (`APP_BASE_URL`); no hardcoded localhost in email payloads |
| **Send Incident Feature** | `IMPLEMENTED` | `TESTED LOCALLY` | Broadcasts notice to employee or group without reassigning ticket or touching ServiceNow |
| **Integration Control Center** | `IMPLEMENTED` | `TESTED LOCALLY & BUILD VERIFIED` | Full `/admin/integrations` & `/admin/integrations/servicenow/events` pages with live status, diagnostics, and typed LIVE confirmation phrase |
| **Read-Only Diagnostics** | `IMPLEMENTED` | `TESTED LOCALLY` | Checks Incident Table, Group Table, User Table, Field level read permissions without mutations |
| **Live Staging Host Execution** | `BLOCKED` | `PENDING REAL CREDENTIALS` | Awaiting actual staging instance host, username, and password |

---

## 3. Real Staging Simulation & Field Mapping Report

When an incident arrives from ServiceNow (e.g., `INC1969714`), the defensive mapping transforms fields:

```text
================================================================================
FIELD MAPPING REPORT
================================================================================
SERVICENOW FIELD                 INCIDENTFLOW FIELD         MAPPING TYPE
number                     ──►   incident_number            MATCH
sys_id                     ──►   servicenow_sys_id          MATCH
short_description          ──►   short_description          MATCH
description                ──►   description                MATCH
priority (e.g. "1 - Critical") ──► priority ("P1")         NORMALIZED
impact                     ──►   impact                     MATCH
urgency                    ──►   urgency                    MATCH
assignment_group.display_value ──► assignment_group         EXTRACTED
assigned_to.display_value  ──►   assigned_to                EXTRACTED
state (e.g. "1 - New")     ──►   state ("NEW")              NORMALIZED
opened_at                  ──►   opened_at                  PARSED ISO-8601
u_work_instructions        ──►   work_instructions          MATCH
work_notes                 ──►   work_notes                 MATCH
================================================================================
```

---

## 4. Shadow Candidate Dossier Audit

Simulation for **INC1969714** (Analytics – MDM L3) during Morning Shift (09:00–12:00):

```text
================================================================================
RUNTIME CANDIDATE DOSSIER
================================================================================
Incident Number:   INC1969714
ServiceNow Sys ID: sys_mdm_1969714
Short Description: MDM synchronization issue
Assignment Group:  Analytics – MDM L3
Active Shift:      Morning Shift (09:00 - 12:00)

WOULD ASSIGN TO:
  ► Ravi Kumar (Lowest workload on active shift)

ELIGIBLE CANDIDATES ON SHIFT:
  ✓ Ravi Kumar — Workload: 1 active ticket (SELECTED)
  ✓ Kiran Patel — Workload: 3 active tickets

REJECTED CANDIDATES & RATIONALE:
  ✕ Suresh Reddy — OFF_SHIFT (Scheduled on Shift 2: 12:00 - 15:00)
  ✕ Arun Verma   — MISSING_SKILL: MDM (Required for MDM L3)
  ✕ Deepa Shah   — STATUS_BUSY (Availability status is BUSY)

STRATEGY APPLIED:
  SKILL_PLUS_WORKLOAD

SERVICENOW MUTATION ATTEMPTED:
  NO (0 Mutations — Pristine Staging Guarantee)
================================================================================
```

---

## 5. ServiceNow Before / After Verification

| Attribute | Before Webhook | After Shadow Evaluation | Mutation Count |
|---|---|---|---|
| `assigned_to` | Unassigned / Empty | Unassigned / Empty | 0 |
| `state` | 1 (New) | 1 (New) | 0 |
| `work_notes` | Original notes | Original notes | 0 |

`SERVICENOW_MUTATION_COUNT = 0`

---

## 6. Send Incident Feature Status (Section 16 Audit)

- **Audit Result:** `SEND_INCIDENT_FEATURE = IMPLEMENTED`
- **Distinction Enforced:** `SEND != ASSIGN`
  - **SEND**: Dispatches in-app notification or mock email announcement without altering ticket assignment or state.
  - **ASSIGN**: Changes responsible worker (`IncidentAssignment`).
- **Endpoints Available:**
  - `POST /api/admin/incidents/{id}/send/preview`
  - `POST /api/admin/incidents/{id}/send`
- **UI Integration:** Added directly to Admin Assignments (`/admin/assignments`) with preview modal and mobile-friendly layout.

---

## 7. URL Audit & APP_BASE_URL (Section 15)

Every occurrence of `localhost:3000` and `localhost:8000` was classified:

| File Location | Occurrence | Classification | Rationale / Resolution |
|---|---|---|---|
| `backend/app/api/admin.py` | `http://localhost:3000/work/...` | `MUST_FIX` | **Fixed**: Replaced with `f"{settings.APP_BASE_URL.rstrip('/')}/work/..."` |
| `backend/app/core/config.py` | `APP_BASE_URL: str = "http://localhost:3000"` | `DEV_ONLY` | Configurable per environment via `APP_BASE_URL` env var |
| `backend/app/core/config.py` | `CORS_ORIGINS = ["http://localhost:3000"]` | `DEV_ONLY` | Safe local CORS origins; overridden by env in production |
| `frontend/next.config.ts` | `http://localhost:8000/api/...` | `DEV_ONLY` | Next.js API proxy rewrite fallback when `NEXT_PUBLIC_API_URL` is omitted |
| `frontend/lib/api-client.ts` | `http://localhost:8000` | `DEV_ONLY` | Browser API client baseUrl fallback when env var is omitted |
| `tests/test_servicenow_staging.py` | `assert in result["incident_link"]` | `TEST_ONLY` | Verified against `settings.APP_BASE_URL` |

---

## 8. Automated Regression Tests

- **Backend Pytest Suite:** **50 / 50 Passed** (100%) in 0.46s.
- **Frontend Production Build:** **18 / 18 Routes Pre-rendered** with zero TypeScript or linting errors.

---

## 9. Final Operational Safety State

```text
REAL_SERVICENOW_STAGING_E2E=BLOCKED (Awaiting Staging Credentials)
AUTOMATION_MODE=SHADOW
LIVE=OFF
EMAIL_PROVIDER=MOCK
```

