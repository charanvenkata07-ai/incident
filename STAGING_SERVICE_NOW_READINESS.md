# IncidentFlow — ServiceNow Staging Readiness & Admin Checklist

**Environment:** STAGING  
**Current Integration Status:** `REAL_SERVICENOW_STAGING_E2E: BLOCKED`  
**Root Cause:** External ServiceNow staging instance is not yet provisioned / hostname is a placeholder (`dev-staging.service-now.com` -> `[Errno 8] nodename nor servname provided, or not known`). Zero fake tests permitted.

---

## 1. Readiness & Verification Matrix

| Component | Status | Details / Evidence |
| :--- | :---: | :--- |
| **REAL INSTANCE** | `CONFIGURED` | Configured to `https://dev-staging.service-now.com` (Unroutable placeholder domain) |
| **CONNECTIVITY** | `BLOCKED` | DNS resolution failed: `[Errno 8] nodename nor servname provided, or not known` |
| **AUTHENTICATION** | `BLOCKED` | Staging credentials contain placeholders (`<PLACEHOLDER_STAGING_PASSWORD>`) |
| **READ ACCESS** | `BLOCKED` | Outbound GET requests to ServiceNow Table API blocked by host unreachability |
| **WEBHOOK INGRESS** | `PASS` | Timing-safe HMAC secret validation, 1MB payload ceiling, replay deduplication |
| **FIELD MAPPING** | `PASS` | 17/17 fields extracted defensively via `ServiceNowMapper` |
| **INCIDENT PERSISTENCE** | `PASS` | Idempotent persistence with deduplication across `sys_id` and `incident_number` |
| **SHADOW ASSIGNMENT** | `PASS` | Shift boundary detection, presence, skill matching, workload scoring, dossier logging |
| **EMPLOYEE WORKFLOW** | `PASS` | Candidate dashboard, work view, `YOUR TASK`, Acknowledge, Start Work, Complete |
| **ZERO MUTATIONS** | `PASS` | 0 outbound mutations executed; all ServiceNow update paths intercepted in `SHADOW` mode |
| **FAILURE HANDLING** | `PASS` | 9/9 failure scenarios handled cleanly with complete audit trails |

---

## 2. Verified Local Capabilities & Readiness Proof

All internal integration layers are fully implemented, defensively tested, and verified across 68 automated test cases:

- **17/17 Field Mappings Verified**: `sys_id`, `number`, `short_description`, `description`, `priority`, `impact`, `urgency`, `category`, `subcategory`, `assignment_group`, `assigned_to`, `caller_id`, `location`, `cmdb_ci`, `state`, `opened_at`, `work_notes`.
- **Zero Mutation Guard Verified**: All outbound mutations (`update_incident`, `update_assignment`, `add_work_note`, `update_state`) are intercepted and returned with `status: "skipped"` when `AUTOMATION_MODE=SHADOW`.
- **Defensive Error Handling Verified**: 9 failure scenarios (invalid secret, duplicate payload, malformed payload, unreachable host, timeout, invalid auth, missing group, unknown group, zero engineers) pass cleanly.
- **Webhook Ingress Verified**: Ingests, validates, deduplicates by `sys_id`/`incident_number`, and logs full audit dossier.
- **End-to-End Business Workflow**: Synthetic tickets ingest seamlessly, resolve shift, evaluate skills and workload, select optimal candidate, populate employee dashboard (`YOUR TASK`), and allow lifecycle progression without requiring engineers to manually copy/paste incident IDs or self-assign.

---

## 3. Requirements Checklist for ServiceNow Administrator

To unblock the real end-to-end integration test, the ServiceNow Administrator must provide and configure the following:

### A. Information Needed from ServiceNow Administrator
1. **ServiceNow Subdomain**: Full HTTPS URL of the TEST or STAGING instance (e.g., `https://dev12345.service-now.com`).
2. **Dedicated Service Account**: Non-interactive user account (e.g., `incidentflow_svc`).
3. **Required Roles**:
   - `itil` (standard incident management access)
   - `rest_service` (REST Table API access)
   - `snc_read_only` (or table-level ACL read permission on `incident`, `sys_user_group`)
4. **Authentication Credentials**:
   - Option 1 (Basic Auth): Username and strong alphanumeric password.
   - Option 2 (OAuth 2.0): Client ID and Client Secret generated under ServiceNow Application Registry.
5. **Assignment Group**: Exact name of the target group in ServiceNow matching IncidentFlow (e.g., `Analytics – MDM L3`).
6. **Network / IP Allowlisting**: Confirm if staging instance requires IP allowlisting for inbound/outbound REST traffic.

### B. Configuration Needed in ServiceNow
1. **Outbound Business Rule / Webhook**:
   - Trigger: Incident `Insert` or `Update` where `assignment_group` equals target group.
   - Target URL: `https://<INCIDENTFLOW_STAGING_DOMAIN>/api/integrations/servicenow/incidents`
   - Headers:
     - `Content-Type: application/json`
     - `X-ServiceNow-Secret: <SHARED_HMAC_SECRET>`

### C. Synthetic Staging Incident for E2E Validation
- Admin creates a single synthetic incident in ServiceNow with:
  - Short Description: `TEST - IncidentFlow Synthetic Staging Verification`
  - Priority: `3 - Moderate`
  - Assignment Group: `Analytics – MDM L3`
  - State: `New` (1)

---

## 4. Step-by-Step Procedure to Unblock E2E Once Credentials Arrive

1. **Update Local Staging Configuration (`backend/.env`)**:
   ```bash
   SERVICENOW_URL="https://<REAL_STAGING_INSTANCE>.service-now.com"
   SERVICENOW_USERNAME="<REAL_STAGING_USER>"
   SERVICENOW_PASSWORD="<REAL_STAGING_PASSWORD>"
   SERVICENOW_WEBHOOK_SECRET="<REAL_SHARED_SECRET>"
   ```

2. **Verify Configuration Gate**:
   ```bash
   python -m scripts.run_real_servicenow_staging_suite
   ```

3. **Trigger Live Connectivity Probe via API**:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/admin/integrations/servicenow/test-connection \
     -H "Authorization: Bearer $TOKEN"
   ```
   - Expect: `{"status":"connected","status_code":200,"records_found":1}`.

4. **Verify Zero Mutation Execution**:
   - Confirm candidate selected in IncidentFlow is logged to audit log.
   - Confirm ticket in ServiceNow retains `assigned_to` empty.
   - Mark gate `REAL_SERVICENOW_STAGING_E2E: PASS`.
