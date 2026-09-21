# IncidentFlow — Staging Deployment Guide & Architecture Topology

**Environment:** STAGING  
**Version:** RC1 (v0.1.0-staging)  
**Safety Profile:** AUTOMATION_MODE=SHADOW | LIVE=OFF | EMAIL_PROVIDER=MOCK | SERVICENOW_MUTATIONS=BLOCKED  

---

## 1. System Architecture & Topology

The staging environment operates on an isolated container network (`incidentflow-staging-net`) preventing unintended traffic to or from external production services.

```
[ ServiceNow TEST/STAGING ]
           │ (HTTPS Inbound Webhook)
           ▼
    ┌────────────────────────┐
    │  Next.js Frontend      │ (Port 3000)
    │  (/admin/integrations) │
    └──────────┬─────────────┘
               │ (HTTP / WebSocket Proxy)
               ▼
    ┌────────────────────────┐         ┌────────────────────────┐
    │  FastAPI Backend API   │◄───────►│  Redis 7.2 Broker      │ (Port 6379)
    │  (Port 8000, 4 workers)│         │  (Queue / PubSub)      │
    └──────────┬─────────────┘         └──────────┬─────────────┘
               │                                  │ (Task Execution)
               │ (Async Connection Pool)          ▼
               │                       ┌────────────────────────┐
               │                       │  Celery Worker Daemon  │
               │                       │  (Concurrency: 4)      │
               ▼                       └────────────────────────┘
    ┌────────────────────────┐
    │  PostgreSQL 16 Engine  │ (Port 5432)
    │  (ACID, Row-Level Lock)│
    └────────────────────────┘
```

### Component Specifications:
1. **PostgreSQL 16**: Relational storage engine with WAL replication. Strict fail-closed configuration prevents SQLite in staging/production.
2. **Redis 7.2**: In-memory broker for Celery async worker queue and WebSocket pub/sub message bus.
3. **FastAPI Backend (Uvicorn)**: Asynchronous REST and WebSocket server with strict environment isolation checks on startup.
4. **Celery Worker**: Asynchronous background processor for dispatching notifications, re-sync retries, and scheduled tasks.
5. **Next.js 15 Frontend**: Server-rendered and statically optimized management console.

---

## 2. Environment Configuration (`backend/.env.staging`)

```env
# Application Environment
APP_NAME="IncidentFlow"
DEBUG=False
ENVIRONMENT="STAGING"
AUTOMATION_MODE="SHADOW"
SHADOW_MODE=True
DRY_RUN_MODE=False

# Database Connectivity (Strictly PostgreSQL in Staging)
DATABASE_URL="postgresql+asyncpg://incidentflow:incidentflow_dev@db-staging:5432/incidentflow"

# Message Broker
REDIS_URL="redis://redis-staging:6379/0"

# Security & Sessions
JWT_SECRET="<SECURE_STAGING_JWT_SECRET_32_CHARS>"
JWT_ALGORITHM="HS256"
JWT_EXPIRATION_MINUTES=480

# CORS & Base URLs
APP_BASE_URL="http://staging.incidentflow.internal:3000"
CORS_ORIGINS=["http://staging.incidentflow.internal:3000","http://localhost:3000"]

# ServiceNow TEST/STAGING Integration (NEVER Target Production)
SERVICENOW_MOCK=False
SERVICENOW_URL="https://your-company-stage.service-now.com"
SERVICENOW_USERNAME="incidentflow_stage_svc"
SERVICENOW_PASSWORD="<STRONG_STAGING_PASSWORD>"
SERVICENOW_CLIENT_ID="<OPTIONAL_OAUTH_CLIENT_ID>"
SERVICENOW_CLIENT_SECRET="<OPTIONAL_OAUTH_CLIENT_SECRET>"
SERVICENOW_WEBHOOK_SECRET="<SHARED_HMAC_WEBHOOK_SECRET>"
ASSIGNMENT_GROUP="Analytics – MDM L3"

# Engine & Worker
DEFAULT_TIMEZONE="Asia/Kolkata"
AUTO_ASSIGNMENT_ENABLED=True
ASSIGNMENT_STRATEGY="SKILL_PLUS_WORKLOAD"

# Communications Safety
EMAIL_PROVIDER="MOCK"
LOG_LEVEL="INFO"
```

---

## 3. Docker Compose Orchestration

The staging profile is defined in `docker-compose.staging.yml`.

### Launching Staging Stack:
```bash
# Build and run containers in detached mode
docker-compose -f docker-compose.staging.yml up -d --build

# Inspect running containers
docker-compose -f docker-compose.staging.yml ps

# Follow container logs
docker-compose -f docker-compose.staging.yml logs -f backend-staging worker-staging
```

### Automated Database Migrations:
The backend service automatically executes Alembic migrations during startup before launching the HTTP server:
```bash
alembic upgrade head
```

---

## 4. Health & Readiness Probes

Kubernetes / Docker Compose health checks ensure traffic is only routed to healthy pods:

### Liveness Probe (`GET /health`):
- Checks application process health.
- Response: `{"status": "HEALTHY", "service": "IncidentFlow", "environment": "STAGING", "automation_mode": "SHADOW"}`

### Readiness Probe (`GET /ready`):
- Performs active database query (`SELECT 1`) and Redis `PING`.
- Response: HTTP 200 when ready, HTTP 503 if PostgreSQL is unavailable.
- Degraded mode: If Redis is unavailable, `/ready` reports `ready: true, redis: "DEGRADED"` to permit critical DB reads while alerting on worker queues.

---

## 5. Graceful Shutdown & Zero In-Flight Task Dropping

To ensure in-flight webhook requests and incident transactions complete cleanly during deployments or scale-downs:
- Both backend and Celery containers are configured with `stop_grace_period: 30s`.
- On `SIGTERM`, FastAPI completes current HTTP transactions before closing database connection pools.
- Celery worker stops accepting new tasks (`worker_shutting_down`) and completes active tasks up to 30 seconds before exiting.
