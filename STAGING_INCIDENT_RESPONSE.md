# IncidentFlow — Staging Incident Response & Triage Guide

**Target Environment:** STAGING  
**Scope:** Triage and remediation procedures for platform infrastructure, integration, and assignment outages.  

---

## 1. Severity Classification Matrix

| Severity | Definition | Target Response | Target Resolution |
| :--- | :--- | :--- | :--- |
| **P1 - Critical** | Database unreachable, webhook ingestion down, data corruption risk. | < 15 minutes | < 1 hour |
| **P2 - High** | Celery worker dead, Redis offline (degraded mode), DLQ buildup (>10). | < 30 minutes | < 2 hours |
| **P3 - Medium** | WebSocket disconnections, degraded assignment latency (>2s). | < 2 hours | < 8 hours |
| **P4 - Low** | Cosmetic frontend reporting defect, non-critical metrics delay. | Next business day | Next sprint |

---

## 2. Emergency Triage Procedures

### Scenario A: Database Down / Connection Refused (HTTP 503)
**Symptoms:** `/ready` returns HTTP 503, logs show `DB Connection Refused`.
1. **Verify PostgreSQL status:**
   ```bash
   pg_isready -h localhost -p 5432
   ```
2. **Check container / daemon logs:**
   ```bash
   docker logs db-staging --tail 100
   ```
3. **Restart database if stuck:**
   ```bash
   docker-compose -f docker-compose.staging.yml restart db-staging
   ```
4. **Re-verify readiness:**
   ```bash
   curl -i http://127.0.0.1:8000/ready
   ```

---

### Scenario B: Redis Down / Broken Pipe
**Symptoms:** `/ready` returns HTTP 200 with `redis: "DEGRADED"`, Celery tasks stall.
1. **Assess Impact:** Backend continues to serve read APIs and ingest webhooks directly to PostgreSQL. WebSocket broadcasts fall back safely.
2. **Inspect Redis logs:**
   ```bash
   docker logs redis-staging --tail 50
   ```
3. **Restart Redis:**
   ```bash
   docker-compose -f docker-compose.staging.yml restart redis-staging
   ```
4. **Verify worker reconnection:**
   ```bash
   docker logs worker-staging --tail 20
   ```

---

### Scenario C: Celery Worker Dead / Task Queue Building
**Symptoms:** Worker heartbeat check fails; background emails and re-syncs do not process.
1. **Check worker process:**
   ```bash
   ps aux | grep celery
   ```
2. **Restart Celery daemon:**
   ```bash
   docker-compose -f docker-compose.staging.yml restart worker-staging
   ```
3. **Verify heartbeat acknowledgement:**
   ```bash
   python -c "from app.workers.tasks import ping_worker; print(ping_worker.delay().get(timeout=5))"
   ```

---

### Scenario D: Webhook Failure Flood / Unauthorized Attack
**Symptoms:** Spike in HTTP 401s on `/api/integrations/servicenow/incidents`, system metrics report high webhook failure counts.
1. **Review unauthorized attempts:**
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/admin/integrations/servicenow/events?status=FAILED | jq .
   ```
2. **Verify HMAC secret configuration:**
   - Confirm if ServiceNow outbound webhook is presenting the correct `X-ServiceNow-Secret` header matching `SERVICENOW_WEBHOOK_SECRET`.
3. **Rate limiting / IP blocking:**
   - If malicious probe detected, block remote IP at edge reverse proxy (Nginx / Cloudflare).

---

### Scenario E: Dead Letter Queue (DLQ) Alert
**Symptoms:** `dead_letter_queue > 0` in `/observability/metrics`.
1. **Query Dead Lettered records:**
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/admin/integrations/servicenow/dlq | jq .
   ```
2. **Analyze failure reason:**
   - E.g., `ServiceNow API 500: Internal Server Error` or `404: Record Not Found`.
3. **Replay DLQ after upstream resolution:**
   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/admin/integrations/servicenow/dlq/retry
   ```

---

### Scenario F: Emergency Platform Circuit Breaker
If the assignment algorithm misbehaves or an unexpected loop occurs:
```bash
curl -X POST http://127.0.0.1:8000/api/admin/automation/pause \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Emergency pause during triage"}'
```
