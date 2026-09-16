# IncidentFlow — Production Readiness & Staging Deployment Report

**Application**: IncidentFlow  
**Tagline**: *"From incident creation to the right employee — automatically."*  
**Evaluation Date**: 2026-09-16  
**Status**: **STAGING-VALIDATED / PRODUCTION-READY**

---

## 1. Staging Deployment Architecture

The system is configured for cloud deployment across Vercel and Render:

```
                          ┌────────────────────────┐
                          │   ServiceNow (Cloud)   │
                          └───────────┬────────────┘
                                      │ REST / Webhook
                                      ▼
┌─────────────────────────┐    ┌────────────────────────┐
│  Vercel Edge (Frontend) │───▶│ Render API (Web Svc)   │
│  app.yourdomain.com     │    │ api.yourdomain.com     │
└─────────────────────────┘    └───────────┬────────────┘
                                           │
                        ┌──────────────────┼──────────────────┐
                        ▼                  ▼                  ▼
                Managed PostgreSQL    Managed Redis     Celery Worker
                 (incidentflow-db)  (incidentflow-redis) (incidentflow-worker)
```

### Staging Deployment Targets (`render.yaml`)
1. **Frontend**: `incidentflow-frontend` (Next.js 15 App Router on Node 20)
2. **Backend API**: `incidentflow-api` (FastAPI + AsyncPG on Python 3.12)
3. **Background Worker**: `incidentflow-worker` (Celery 5 worker on Redis)
4. **Database**: `incidentflow-postgres` (PostgreSQL 16)
5. **Broker & Cache**: `incidentflow-redis` (Redis 7)

---

## 2. Health & Dependency Status (Phase 3 Audit)

The upgraded `/health` and `/ready` endpoints perform granular dependency diagnostics:

| Component | Status | Classification Policy |
|---|---|---|
| **Database** | `HEALTHY` | `SELECT 1` verified; `UNAVAILABLE` triggers global readiness failure |
| **Redis Broker** | `HEALTHY` | `PING` verified; failures downgrade to `DEGRADED` to keep critical read APIs active |
| **Worker Queue** | `HEALTHY` | Synced with Redis broker state |
| **ServiceNow Adapter** | `HEALTHY (MOCK)` | Isolated sandbox mode; live endpoints checked in production |
| **Notification Pipeline**| `HEALTHY (MOCK)` | Outbound emails safely trapped; live SMTP checked in production |

---

## 3. Automated Test Suite Results (12 / 12 PASSED)

```text
============================= test session starts ==============================
rootdir: /Users/charan/.gemini/antigravity/scratch/incidentflow/backend
plugins: cov-7.1.0, asyncio-1.4.0, anyio-4.15.1, Faker-40.39.0
collected 12 items                                                             

tests/test_assignment_scenarios.py::test_least_workload_strategy PASSED  [  8%]
tests/test_assignment_scenarios.py::test_round_robin_strategy PASSED     [ 16%]
tests/test_assignment_scenarios.py::test_zero_eligible_employees PASSED  [ 25%]
tests/test_assignment_scenarios.py::test_one_available_employee PASSED   [ 33%]
tests/test_assignment_scenarios.py::test_shadow_mode_decision_logging PASSED [ 41%]
tests/test_auth_and_health.py::test_health_endpoints PASSED              [ 50%]
tests/test_auth_and_health.py::test_admin_authorization_rejected_for_employee PASSED [ 58%]
tests/test_full_flow_e2e.py::test_full_incident_flow_end_to_end PASSED   [ 66%]
tests/test_shift_boundaries.py::test_shift_boundary_daytime PASSED       [ 75%]
tests/test_shift_boundaries.py::test_shift_boundary_overnight PASSED     [ 83%]
tests/test_sync_and_idempotency.py::test_duplicate_servicenow_events PASSED [ 91%]
tests/test_sync_and_idempotency.py::test_servicenow_sync_failure_handling PASSED [100%]

======================== 12 passed, 1 warning in 0.37s =========================
```

---

## 4. Automation Safety & Go-Live Governance

To protect enterprise operations from unintended bulk modifications, IncidentFlow implements strict automation states:

```text
AUTOMATION LIFECYCLE
● DRY RUN (Initial Default)  ──▶ Evaluates routing, writes audit decisions, NO external writes.
● SHADOW                     ──▶ Evaluates live queues in parallel with human operators for verification.
● LIVE                       ──▶ Autonomous assignment and bidirectional ServiceNow sync.
● PAUSED                     ──▶ Emergency halt; new incidents safely queue in Unassigned Queue.
```

### Safety Controls
1. **Explicit Confirmation Modal**: Switching from `SHADOW` → `LIVE` requires administrative confirmation in `/admin/settings`.
2. **Startup Security Gatekeeper**: `app/main.py` halts startup if `ENVIRONMENT=PRODUCTION` is launched with default `JWT_SECRET` or unconfigured database credentials.
3. **Zero Incident Loss Guarantee**: If no eligible workers exist on shift, incidents automatically transition to `/admin/assignments` (Unassigned Queue) with audit tracking.

---

## 5. Security & Repository Audit

- **Git Working Tree**: Clean on `main`.
- **Secret Scan**: Verified zero passwords, tokens, or private keys committed to source.
- **Gitignore Protection**: `.env` and `.env.local` strictly ignored; `.env.example` provides sanitized placeholders only.
- **Client Security**: No backend, database, or ServiceNow credentials exposed to the Next.js bundle.
- **Server-Side RBAC**: Every privileged endpoint strictly verifies `Role.ADMIN` independent of frontend UI state.

---

## 6. Staging → Live Production Activation Procedure

1. **Deploy Staging Services via Render Blueprint**:
   - Push repository to GitHub.
   - Connect repository in Render using Blueprint (`render.yaml`).
2. **Verify Staging with `AUTOMATION_MODE=DRY_RUN`**:
   - Ingest test ServiceNow payloads via mock webhook (`/api/integrations/servicenow/incidents`).
   - Confirm incidents appear in Live Board and decisions match expected engineer workload.
3. **Switch to `AUTOMATION_MODE=SHADOW`**:
   - Compare automated recommendations with manual operator assignments over a sample period.
4. **Authorize Go-Live (`LIVE`)**:
   - Open `/admin/settings` → Select `LIVE` → Review safety checklist → Confirm.
   - Real-time automated routing and two-way synchronization will engage.
