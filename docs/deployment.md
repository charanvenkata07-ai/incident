# Deployment Guide

## Architecture Overview

```
                 SERVICE NOW
                      │
                      │ REST / Events
                      ▼
              ┌───────────────┐
              │    Render      │
              │    FastAPI     │
              └───────┬───────┘
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
       Shift       Assignment   Notification
       Engine        Engine        Service
          │           │
          └─────┬─────┘
                ▼
          PostgreSQL     Redis
                │
                ▼
             WebSocket
                │
                ▼
        ┌─────────────────┐
        │     Vercel       │
        │     Next.js      │
        └────────┬────────┘
                 │
        ┌────────┴─────────┐
        ▼                  ▼
    Employee            Admin
    Portal              Portal
```

## Domain Architecture

| Service | Domain | Platform |
|---------|--------|----------|
| Frontend | `app.example.com` | Vercel |
| Backend API | `api.example.com` | Render |
| Database | Internal | Render PostgreSQL |
| Redis | Internal | Managed Redis |

---

## 1. GitHub Repository Setup

```bash
# Initialize repository
git init
git add .
git commit -m "Initial commit: IncidentFlow"
git remote add origin https://github.com/your-org/incidentflow.git
git push -u origin main
```

### Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production deployments |
| `staging` | Staging environment |
| `develop` | Development integration |

---

## 2. Render Backend Deployment

### 2.1 PostgreSQL Database

1. Go to Render Dashboard → **New** → **PostgreSQL**
2. Configure:
   - **Name**: `incidentflow-db`
   - **Database**: `incidentflow`
   - **User**: `incidentflow`
   - **Region**: Choose closest to your users
   - **Plan**: Starter or Standard (production)
3. Copy the **Internal Database URL** for backend config

### 2.2 Redis

Option A: Render Redis (if available in your region)
1. **New** → **Redis**
2. **Name**: `incidentflow-redis`
3. Copy the connection URL

Option B: Upstash Redis
1. Create account at https://upstash.com
2. Create Redis database
3. Copy the connection URL

### 2.3 Web Service (FastAPI API)

1. **New** → **Web Service**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `incidentflow-api`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -e ".[dev]" && alembic upgrade head`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Starter or Standard

4. Environment Variables:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/incidentflow` |
| `REDIS_URL` | `redis://...` |
| `JWT_SECRET` | Generate: `openssl rand -hex 32` |
| `CORS_ORIGINS` | `["https://app.example.com"]` |
| `APP_NAME` | `IncidentFlow` |
| `DEBUG` | `false` |
| `LOG_LEVEL` | `INFO` |
| `SERVICENOW_URL` | Your ServiceNow instance URL |
| `SERVICENOW_USERNAME` | ServiceNow integration user |
| `SERVICENOW_PASSWORD` | ServiceNow integration password |
| `SERVICENOW_MOCK` | `false` (production) |
| `DEFAULT_TIMEZONE` | `Asia/Kolkata` |
| `AUTO_ASSIGNMENT_ENABLED` | `true` |
| `ASSIGNMENT_STRATEGY` | `SKILL_PLUS_WORKLOAD` |

### 2.4 Background Worker

1. **New** → **Background Worker**
2. Connect same repository
3. Configure:
   - **Name**: `incidentflow-worker`
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -e .`
   - **Start Command**: `celery -A app.workers.celery_app worker --loglevel=info`
4. Same environment variables as the web service

### 2.5 Health Checks

Configure Render health check path: `/health`

The API exposes:
- `GET /health` — Basic health check
- `GET /ready` — Full readiness check (DB + Redis)

---

## 3. Vercel Frontend Deployment

### 3.1 Connect Repository

1. Go to https://vercel.com
2. **Import Project** → Select your GitHub repository
3. Configure:
   - **Framework**: Next.js
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `.next`

### 3.2 Environment Variables

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://api.example.com` |

### 3.3 Custom Domain

1. Go to Project Settings → Domains
2. Add `app.example.com`
3. Configure DNS: CNAME to `cname.vercel-dns.com`

### 3.4 Auto-Deploy

Vercel automatically deploys on push to `main`.

---

## 4. ServiceNow Integration

### 4.1 ServiceNow Configuration

1. Create an integration user in ServiceNow
2. Assign appropriate roles (itil, rest_api_explorer)
3. Configure a Business Rule or Flow to send incidents to IncidentFlow:

```
Trigger: When incident is created
Action: REST Message to https://api.example.com/api/integrations/servicenow/incidents
Method: POST
Authentication: API key or OAuth
```

### 4.2 Webhook Payload

ServiceNow should send:
```json
{
  "sys_id": "abc123",
  "number": "INC1969714",
  "short_description": "MDM synchronization issue",
  "description": "Detailed description...",
  "priority": "3",
  "impact": "2",
  "urgency": "2",
  "category": "MDM",
  "assignment_group": {
    "display_value": "Analytics – MDM L3"
  },
  "state": "1",
  "opened_at": "2026-09-16 09:42:00"
}
```

### 4.3 Field Mappings

Field mappings are configurable via the admin settings. Default mappings:

| ServiceNow Field | IncidentFlow Field |
|---|---|
| `number` | `incident_number` |
| `sys_id` | `servicenow_sys_id` |
| `short_description` | `short_description` |
| `priority` | `priority` (1→P1, 2→P2, 3→P3, 4→P4) |
| `assignment_group.display_value` | `assignment_group` |
| `state` | `state` (mapped) |

### 4.4 Two-Way Sync

After IncidentFlow assigns an employee:
1. IncidentFlow updates ServiceNow's `assigned_to` field
2. ServiceNow changes are polled or received via webhook
3. Conflicts are detected and logged

---

## 5. CORS Configuration

Backend CORS must allow only the production frontend origin:

```python
CORS_ORIGINS=["https://app.example.com"]
```

For staging:
```python
CORS_ORIGINS=["https://staging.app.example.com"]
```

---

## 6. SSL/HTTPS

- Vercel: Automatic HTTPS
- Render: Automatic HTTPS
- All API communication uses HTTPS in production

---

## 7. Monitoring

### Health Endpoints

```bash
# Basic health
curl https://api.example.com/health

# Readiness (DB + Redis)
curl https://api.example.com/ready
```

### Logs

- Render: Dashboard → Logs
- Vercel: Dashboard → Functions → Logs
- Structured JSON logs from backend

### Key Metrics to Monitor

- Assignment latency (time from incident creation to assignment)
- ServiceNow sync failure rate
- Worker queue depth
- API response times
- WebSocket connection count
- Unassigned incident count

---

## 8. Database Migrations

```bash
# Run migrations (done automatically on deploy via build command)
cd backend
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Rollback
alembic downgrade -1
```

---

## 9. Backup & Recovery

### Database Backups

Render PostgreSQL provides:
- Automatic daily backups (Standard plan+)
- Point-in-time recovery

### Manual Backup

```bash
pg_dump -Fc $DATABASE_URL > backup.dump
pg_restore -d $DATABASE_URL backup.dump
```

---

## 10. Environment Matrix

| Setting | Local | Staging | Production |
|---------|-------|---------|------------|
| `DEBUG` | `true` | `false` | `false` |
| `SERVICENOW_MOCK` | `true` | `true` | `false` |
| `DRY_RUN_MODE` | `false` | `true` | `false` |
| `SHADOW_MODE` | `false` | `true` | `false` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `INFO` |
| `CORS_ORIGINS` | `localhost:3000` | staging URL | production URL |

---

## 11. Production Checklist

- [ ] JWT_SECRET is a strong random value (not the default)
- [ ] CORS_ORIGINS contains only production frontend URL
- [ ] SERVICENOW_MOCK is `false`
- [ ] DEBUG is `false`
- [ ] Database backups are configured
- [ ] Health check monitoring is active
- [ ] SSL certificates are valid
- [ ] ServiceNow credentials are set as Render secrets
- [ ] Worker is running and processing jobs
- [ ] Redis is accessible from web service and worker
- [ ] DRY_RUN_MODE testing completed before enabling auto-assignment
- [ ] Audit logging is verified
- [ ] Rate limiting is configured
- [ ] Error tracking is set up (Sentry recommended)
