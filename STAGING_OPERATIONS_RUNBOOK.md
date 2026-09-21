# IncidentFlow — Staging Operations Runbook

**Audience:** Site Reliability Engineers (SRE), Platform Administrators, Operations Engineers  
**Target Environment:** STAGING  
**System Base URL:** `http://127.0.0.1:8000` (API) / `http://localhost:3000` (UI)  

---

## 1. Daily Operations Checklist

Every operational cycle (beginning of shift / daily handover), the on-call engineer must complete the following 4-step checklist:

1. **System Health Verification**:
   ```bash
   curl -s http://127.0.0.1:8000/ready | jq .
   ```
   - Verify `ready: true` and all components (`database`, `redis`, `worker`) report `HEALTHY`.

2. **Telemetry & Metric Audit**:
   ```bash
   TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@incidentflow.dev","password":"<ADMIN_PASSWORD>"}' | jq -r .access_token)

   curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/admin/observability/metrics | jq .
   ```
   - Verify `dead_letter_queue: 0`.
   - Verify `database_health` and `redis_health` are `HEALTHY`.
   - Check `assignment_telemetry.unassigned_incidents`.

3. **Active Shift & Roster Coverage Check**:
   - Access `http://localhost:3000/admin/employees`.
   - Ensure at least 1 engineer per active team is marked `AVAILABLE` and `Checked-in`.

4. **Celery Worker Ping**:
   ```bash
   python -c "from app.workers.tasks import ping_worker; print(ping_worker.delay().get(timeout=5))"
   ```
   - Expect: `WORKER_HEARTBEAT_ACK`.

---

## 2. Emergency Automation Controls

IncidentFlow provides instant API-level circuit breakers to stop automatic ticket routing without taking down the web server or dropping webhooks:

### Emergency Pause:
```bash
curl -X POST http://127.0.0.1:8000/api/admin/automation/pause \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Manual intervention required during upstream maintenance"}'
```
*Effect:* Incoming ServiceNow webhooks are still ingested, validated, and stored in state `NEW`, but zero automatic assignment decisions or notifications occur.

### Automation Resume:
```bash
curl -X POST http://127.0.0.1:8000/api/admin/automation/resume \
  -H "Authorization: Bearer $TOKEN"
```
*Effect:* Restores automatic ticket evaluation and assignment.

---

## 3. Worker Scaling & Queue Monitoring

### Inspecting Pending Tasks:
```bash
celery -A app.workers.celery_app inspect active
celery -A app.workers.celery_app inspect reserved
```

### Scaling Worker Concurrency:
In high-throughput staging tests, increase concurrency via:
```bash
celery -A app.workers.celery_app worker --loglevel=info --concurrency=8
```

---

## 4. Log Analysis & Audit Trail

IncidentFlow uses structured JSON logging via `structlog`. Every HTTP request, Celery job, and assignment decision includes a unique `request_id`.

### Sample Ingestion Log:
```json
{
  "event": "servicenow_webhook_ingested",
  "incident_number": "INC1969714",
  "sys_id": "sys_mdm_999",
  "is_new": true,
  "request_id": "a988d4c0-0f2c-473d-82d2-8b43b355d7a8",
  "timestamp": "2026-09-17T14:15:30Z"
}
```

### Inspecting Lifecycle & Shadow Dossier for an Incident:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/incidents/INC1969714/lifecycle | jq .
```
