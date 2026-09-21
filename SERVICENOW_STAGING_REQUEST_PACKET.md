# IncidentFlow — ServiceNow Staging Integration Request & Implementation Packet

> **Document Type:** Formal Work Order & Technical Integration Specification  
> **Target Audience:** ServiceNow Administrator / Platform Operations Team  
> **Safety State:** `AUTOMATION_MODE=SHADOW` | `LIVE=OFF` | `EMAIL_PROVIDER=MOCK`  
> **Zero Plaintext Credentials Guarantee:** Credentials must be placed directly into the staging secret manager/`backend/.env`. Never transmit credentials via chat or unencrypted channels.

---

## 1. Executive Summary & Objective

IncidentFlow requires integration with a **dedicated ServiceNow TEST / STAGING instance** to validate:
1. Inbound incident webhook ingestion from ServiceNow Business Rules.
2. Read-only Table API connectivity and diagnostic incident polling.
3. Shift- and workload-based autonomous candidate matching under **SHADOW** mode (0 outbound ServiceNow mutations).

---

## 2. Integration Requirements Checklist

| Requirement | Specification | Action by ServiceNow Admin |
| :--- | :--- | :--- |
| **1. HTTPS Instance URL** | Dedicated non-production instance (`https://<instance>.service-now.com` or Developer PDI `https://devXXXXX.service-now.com`) | Provide hostname and confirm TLS 1.2+ |
| **2. Dedicated Service Account** | User ID: `incidentflow_svc`<br>Name: `IncidentFlow Service Account`<br>`Web service access only = true` | Create user in `sys_user` |
| **3. Authentication Method** | **Basic Auth** (Recommended for Staging) or **OAuth 2.0 Client Credentials** | Set strong password or generate OAuth Client ID & Secret |
| **4. Required Roles & Permissions** | • `itil`<br>• `rest_service`<br>• `snc_read_only` (or Table API Read on `incident`, `sys_user_group`, `sys_user`) | Assign roles to `incidentflow_svc` |
| **5. Target Assignment Group** | `Analytics – MDM L3` (or ServiceNow sys_id mapped to group) | Confirm group exists in `sys_user_group` |
| **6. Webhook Business Rule** | Outbound HTTPS POST on Incident `Insert` and `Update` where `assignment_group` matches target group | Deploy Async Business Rule (Script below) |
| **7. Shared Webhook Secret** | Shared HMAC Secret token passed in `X-ServiceNow-Secret` header | Configure in Business Rule and share via secure channel |
| **8. Network & IP Allowlisting** | Outbound HTTPS from IncidentFlow to ServiceNow (:443); Inbound HTTPS from ServiceNow to IncidentFlow webhook | Confirm if ServiceNow staging instance requires IP allowlisting |

---

## 3. Webhook Business Rule Specification

### Business Rule Details
- **Name:** `IncidentFlow Outbound Webhook`
- **Table:** `Incident [incident]`
- **When:** `async` (or `after`)
- **Insert:** `true`
- **Update:** `true`
- **Filter Conditions:**
  - `Assignment group` **is** `Analytics – MDM L3`
  - *Optional:* `State` **is not** `Closed`

### Script (Advanced)
```javascript
(function executeRule(current, previous /*null when async*/) {
    try {
        var request = new sn_ws.RESTMessageV2();
        
        // Target Staging Ingress Endpoint
        request.setEndpoint('https://<INCIDENTFLOW_STAGING_INGRESS>/api/integrations/servicenow/incidents');
        request.setHttpMethod('POST');
        request.setRequestHeader('Content-Type', 'application/json');
        request.setRequestHeader('X-ServiceNow-Secret', '<SHARED_WEBHOOK_SECRET>');

        var payload = {
            sys_id: current.getValue('sys_id'),
            number: current.getValue('number'),
            short_description: current.getValue('short_description'),
            description: current.getValue('description'),
            priority: current.getDisplayValue('priority'),
            impact: current.getDisplayValue('impact'),
            urgency: current.getDisplayValue('urgency'),
            category: current.getValue('category'),
            subcategory: current.getValue('subcategory'),
            assignment_group: {
                display_value: current.assignment_group.getDisplayValue()
            },
            assigned_to: {
                display_value: current.assigned_to.getDisplayValue()
            },
            caller_id: {
                display_value: current.caller_id.getDisplayValue()
            },
            location: {
                display_value: current.location.getDisplayValue()
            },
            cmdb_ci: {
                display_value: current.cmdb_ci.getDisplayValue()
            },
            state: current.getDisplayValue('state'),
            opened_at: current.getValue('opened_at'),
            work_notes: current.work_notes.getJournalEntry(1),
            comments: current.comments.getJournalEntry(1),
            u_work_instructions: current.getValue('u_work_instructions') || current.getValue('description')
        };

        request.setRequestBody(JSON.stringify(payload));
        var response = request.execute();
        var httpStatus = response.getStatusCode();
        gs.info('[IncidentFlow] Dispatched webhook for ' + current.number + ' - HTTP Status: ' + httpStatus);
    } catch (ex) {
        gs.error('[IncidentFlow] Failed to dispatch webhook for ' + current.number + ': ' + ex.getMessage());
    }
})(current, previous);
```

---

## 4. Synthetic Staging Test Incident Definition

Please create **ONE** synthetic test incident in ServiceNow:

- **Short Description:** `TEST - IncidentFlow Synthetic Staging Verification`
- **Description:** `Automated synthetic probe for IncidentFlow staging E2E integration.`
- **Priority:** `3 - Moderate`
- **Impact:** `2 - Medium`
- **Urgency:** `2 - Medium`
- **Category:** `Database`
- **Subcategory:** `Performance`
- **Assignment Group:** `Analytics – MDM L3`
- **State:** `New` (1)
- **assigned_to:** *(Leave empty)*
- **Work Notes:** `Synthetic verification ticket generated for staging onboarding.`
- **Work Instructions:** `Inspect staging database connection pool metrics and restart pool workers if idle connection threshold exceeded.`

---

## 5. Local Staging Activation Procedure (Zero-Secret Chat Rule)

Once the administrator provisions the staging instance and service account, **do NOT post credentials into chat**. Follow these steps:

1. **Populate `backend/.env` locally**:
   ```env
   SERVICENOW_URL="https://<REAL_STAGING_INSTANCE>.service-now.com"
   SERVICENOW_USERNAME="incidentflow_svc"
   SERVICENOW_PASSWORD="<REAL_SERVICE_ACCOUNT_PASSWORD>"
   SERVICENOW_WEBHOOK_SECRET="<CONFIGURED_SHARED_SECRET>"
   ```

2. **Execute Staging Verification Suite**:
   ```bash
   python -m scripts.run_real_servicenow_staging_suite
   ```

3. **Verify Expected Output**:
   ```text
   SERVICENOW_URL_CONFIGURED           : True
   SERVICENOW_TARGET_HOST (Sanitized)  : <REAL_STAGING_INSTANCE>.service-now.com
   SERVICENOW_AUTH_CONFIGURED          : True
   SERVICENOW_WEBHOOK_SECRET_CONFIGURED: True
   PLACEHOLDERS_DETECTED               : False

   --- 2. REAL OUTBOUND CONNECTION ATTEMPT ---
   Endpoint HTTP Status                : 200
   Connection Result                   : PASS
   Status                              : connected

   FINAL INTEGRATION GATE STATUS:
     REAL_SERVICENOW_STAGING_E2E : PASS
   ```
