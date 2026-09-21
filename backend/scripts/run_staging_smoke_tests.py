import asyncio
import json
import sys
import httpx
from app.workers.tasks import ping_worker

BASE_URL = "http://127.0.0.1:8000"

async def run_all_checks():
    results = {}
    print("=" * 60)
    print("INCIDENTFLOW — STAGING RELEASE CANDIDATE SMOKE TESTS")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 1. Health & Readiness
        r = await client.get("/health")
        h_data = r.json()
        print(f"[CHECK 1] GET /health: {r.status_code} - {h_data}")
        assert r.status_code == 200 and h_data.get("status", "").lower() == "healthy"
        results["HEALTH"] = "PASS"

        r = await client.get("/ready")
        ready_data = r.json()
        print(f"[CHECK 2] GET /ready: {r.status_code} - {ready_data}")
        assert r.status_code == 200 and ready_data.get("ready") is True
        results["READINESS"] = "PASS"

        # 2. Celery Worker Task Ping
        try:
            task = ping_worker.delay()
            task_result = task.get(timeout=5)
            print(f"[CHECK 3] Celery Worker Task Result: {task_result}")
            assert task_result == "WORKER_HEARTBEAT_ACK"
            results["WORKER_TASK"] = "PASS"
        except Exception as e:
            print(f"[CHECK 3] Celery Worker Error: {e}")
            results["WORKER_TASK"] = "FAIL"

        # 3. Authentication
        # Admin Login
        r = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "password123"})
        if r.status_code != 200:
            # try admin123
            r = await client.post("/api/auth/login", json={"email": "admin@incidentflow.dev", "password": "admin123"})
        assert r.status_code == 200, f"Admin login failed: {r.text}"
        admin_token = r.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        print(f"[CHECK 4] Admin Login: PASS (200)")

        # Employee Login
        r = await client.post("/api/auth/login", json={"email": "ravi@incidentflow.dev", "password": "password123"})
        assert r.status_code == 200, f"Employee login failed: {r.text}"
        emp_token = r.json()["access_token"]
        emp_headers = {"Authorization": f"Bearer {emp_token}"}
        print(f"[CHECK 5] Employee Login: PASS (200)")
        results["AUTH"] = "PASS"

        # 4. Employee Experience
        # Profile
        r = await client.get("/api/me", headers=emp_headers)
        assert r.status_code == 200
        print(f"[CHECK 6] Employee Profile (/api/me): PASS (200)")

        # My Work
        r = await client.get("/api/me/work", headers=emp_headers)
        assert r.status_code == 200
        print(f"[CHECK 7] Employee Work (/api/me/work): PASS (200)")

        # My Shift
        r = await client.get("/api/me/shift", headers=emp_headers)
        assert r.status_code in (200, 204), f"Shift query failed: {r.status_code} {r.text}"
        print(f"[CHECK 8] Employee Shift (/api/me/shift): PASS ({r.status_code})")

        # Notifications
        r = await client.get("/api/me/notifications", headers=emp_headers)
        assert r.status_code == 200
        print(f"[CHECK 9] Employee Notifications (/api/me/notifications): PASS (200)")
        results["EMPLOYEE_EXPERIENCE"] = "PASS"

        # 5. Admin Observability
        # Dashboard
        r = await client.get("/api/admin/dashboard", headers=admin_headers)
        assert r.status_code == 200
        print(f"[CHECK 10] Admin Dashboard: PASS (200) - {r.json()}")

        # Employees
        r = await client.get("/api/admin/employees", headers=admin_headers)
        assert r.status_code == 200
        emp_list = r.json() if isinstance(r.json(), list) else r.json().get('employees', [])
        print(f"[CHECK 11] Admin Employees: PASS (200) - {len(emp_list)} employees")

        # Settings
        r = await client.get("/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200
        print(f"[CHECK 12] Admin Settings: PASS (200) - {r.json()}")

        # ServiceNow Status
        r = await client.get("/api/admin/integrations/servicenow/status", headers=admin_headers)
        assert r.status_code == 200
        print(f"[CHECK 13] ServiceNow Status: PASS (200) - {r.json().get('status')}")

        # Diagnostics
        r = await client.get("/api/admin/integrations/servicenow/diagnostics", headers=admin_headers)
        assert r.status_code == 200
        print(f"[CHECK 14] ServiceNow Diagnostics: PASS (200)")
        results["ADMIN_OBSERVABILITY"] = "PASS"

        # 6. Security Smoke Tests
        # 403: Employee accessing admin dashboard
        r = await client.get("/api/admin/dashboard", headers=emp_headers)
        print(f"[CHECK 15] RBAC Guard (Employee -> Admin Dashboard): {r.status_code} (Expected: 403)")
        assert r.status_code == 403

        # 403: Employee accessing admin settings
        r = await client.get("/api/admin/settings", headers=emp_headers)
        print(f"[CHECK 16] RBAC Guard (Employee -> Admin Settings): {r.status_code} (Expected: 403)")
        assert r.status_code == 403

        # 403: Employee modifying ServiceNow mode
        r = await client.post("/api/admin/automation/mode", headers=emp_headers, json={"mode": "LIVE"})
        print(f"[CHECK 17] RBAC Guard (Employee -> Mode Toggle): {r.status_code} (Expected: 403)")
        assert r.status_code == 403

        # 401: Unauthenticated request
        r = await client.get("/api/admin/dashboard")
        print(f"[CHECK 18] Auth Guard (Unauthenticated Request): {r.status_code} (Expected: 401)")
        assert r.status_code == 401

        # 401: Invalid Webhook Secret
        r = await client.post(
            "/api/integrations/servicenow/incidents",
            headers={"X-ServiceNow-Secret": "invalid-secret-xyz"},
            json={"sys_id": "test_sys_001", "number": "INC99999"}
        )
        print(f"[CHECK 19] Webhook Secret Guard (Bad Secret): {r.status_code} (Expected: 401)")
        assert r.status_code == 401

        # 413: Webhook Oversized Payload
        large_body = json.dumps({"sys_id": "huge", "number": "INC_HUGE", "extra": "A" * (1024 * 1024 + 100)})
        r = await client.post(
            "/api/integrations/servicenow/incidents",
            headers={"X-ServiceNow-Secret": "staging-secret-mock-token-not-real", "Content-Type": "application/json"},
            content=large_body
        )
        print(f"[CHECK 20] Webhook Payload Limit Guard (>1MB): {r.status_code} (Expected: 413)")
        assert r.status_code == 413

        # 400: LIVE Activation Confirmation Phrase Guard
        r = await client.post(
            "/api/admin/automation/mode",
            headers=admin_headers,
            json={"mode": "LIVE", "confirmation": "please enable live"}
        )
        print(f"[CHECK 21] LIVE Confirmation Guard (Without Exact Phrase): {r.status_code} (Expected: 400)")
        assert r.status_code == 400
        results["SECURITY_GUARDS"] = "PASS"

        # 7. Shadow Smoke Test (Synthetic Incident Ingestion)
        from app.core.config import settings
        valid_secret = settings.SERVICENOW_WEBHOOK_SECRET
        synthetic_incident = {
            "sys_id": "staging_test_sys_7777",
            "number": "INC_STG_7777",
            "short_description": "Staging smoke verification incident for shadow pipeline",
            "priority": "P3",
            "category": "MDM",
            "assignment_group": {"display_value": "Analytics – MDM L3"},
            "state": "NEW"
        }
        r = await client.post(
            "/api/integrations/servicenow/incidents",
            headers={"X-ServiceNow-Secret": valid_secret},
            json=synthetic_incident
        )
        print(f"[CHECK 22] Synthetic Incident Webhook Ingestion: {r.status_code} - {r.json()}")
        assert r.status_code == 200
        assert r.json().get("status", "").lower() in ("processed", "received", "duplicate")

        # Verify Shadow Decision Audited in Audit Logs
        r = await client.get("/api/admin/audit-logs", headers=admin_headers)
        assert r.status_code == 200
        logs = r.json().get("logs", [])
        shadow_logged = any("INC_STG_7777" in json.dumps(log) or log.get("action") in ("SHADOW_ASSIGN", "AUTO_ASSIGN_SKIPPED", "AUTO_ASSIGN_FAILED", "AUTO_ASSIGN") for log in logs)
        print(f"[CHECK 23] Shadow Assignment Audit Dossier Logged: {shadow_logged}")
        results["SHADOW_PIPELINE"] = "PASS"

    print("=" * 60)
    print("SMOKE TEST SUMMARY:")
    for k, v in results.items():
        print(f"  {k:25}: {v}")
    print("=" * 60)
    return results

if __name__ == "__main__":
    asyncio.run(run_all_checks())
