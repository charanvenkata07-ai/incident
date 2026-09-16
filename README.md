# IncidentFlow

> **From incident creation to the right employee — automatically.**

IncidentFlow is a modern enterprise incident assignment and employee work-management platform that integrates with ServiceNow. It eliminates the manual workflow of copying incident IDs, finding dashboards, and self-assigning work.

## How It Works

```
ServiceNow creates incident
        ↓
IncidentFlow receives incident
        ↓
Determines current active shift
        ↓
Finds eligible employees (present, available, skilled)
        ↓
Automatically assigns to best-fit employee
        ↓
Synchronizes assignment with ServiceNow
        ↓
Notifies employee (in-app + email)
        ↓
Employee opens IncidentFlow
        ↓
Incident + assigned work is immediately visible
        ↓
Employee acknowledges → starts work
        ↓
Status synchronizes back to ServiceNow
```

**The employee never needs to manually type or paste an Incident ID.**

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Framer Motion |
| **Backend** | Python, FastAPI, Pydantic, SQLAlchemy 2.0 |
| **Database** | PostgreSQL 16 |
| **Queue** | Redis + Celery |
| **Real-time** | WebSockets |
| **Integration** | ServiceNow REST APIs |
| **Deployment** | Vercel (frontend) + Render (backend) |

---

## Features

### Employee Portal
- **Dashboard** — Greeting, shift status, active incidents at a glance
- **My Work** — Filterable list of assigned incidents with task details
- **Incident Details** — Full incident view with YOUR TASK section, actions (Acknowledge/Start/Complete), activity timeline
- **My Shift** — Current shift info, team presence
- **Notifications** — Real-time in-app notifications

### Admin Portal
- **Dashboard** — Active incidents, unassigned count, employee status, live assignments
- **Employee Management** — Team, skills, availability, workload overview
- **Shift Management** — Create/edit shifts, assign employees, timezone support
- **Assignment Management** — View all assignments, reassign, unassign, manual assign
- **Analytics** — Incidents per day/shift/employee, assignment types, response times
- **Audit Logs** — Full audit trail of all actions
- **Settings** — Assignment automation control, strategy selection, dry-run/shadow mode, system health

### Assignment Engine
- **4 Strategies**: Round Robin, Least Workload, Skill-Based, Skill + Workload
- **Eligibility Checks**: Shift → Presence → Availability → Team → Skills → Workload
- **Race Condition Protection**: Row-level locking for concurrent assignments
- **Dry Run Mode**: Calculate assignments without executing
- **Shadow Mode**: Compare AI vs human assignments

### ServiceNow Integration
- Bidirectional sync (incidents ↔ assignments ↔ status)
- Configurable field mappings
- Conflict detection
- Retry with exponential backoff
- Mock adapter for development

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL 16
- Redis 7

### Option A: Using Docker (PostgreSQL + Redis)

```bash
docker compose up -d
```

### Option B: Native Install

```bash
# macOS
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis

# Create database
createdb incidentflow
```

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment variables
cp .env.example .env

# Run database migrations
alembic upgrade head

# Seed development data
python -m scripts.seed_dev

# Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy environment variables
cp .env.example .env.local

# Start development server
npm run dev
```

### Start Worker (optional, for background jobs)

```bash
cd backend
celery -A app.workers.celery_app worker --loglevel=info
```

### Access the Application

| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Frontend |
| http://localhost:8000 | Backend API |
| http://localhost:8000/docs | API Documentation (Swagger) |
| http://localhost:8000/redoc | API Documentation (ReDoc) |

### Development Accounts

| Email | Password | Role |
|-------|----------|------|
| admin@incidentflow.dev | admin123 | Admin |
| supervisor@incidentflow.dev | super123 | Supervisor |
| ravi@incidentflow.dev | password123 | Employee |
| kiran@incidentflow.dev | password123 | Employee |
| suresh@incidentflow.dev | password123 | Employee |

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://incidentflow:incidentflow_dev@localhost:5432/incidentflow` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret key for JWT tokens | `dev-secret-change-in-production` |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array) | `["http://localhost:3000"]` |
| `SERVICENOW_URL` | ServiceNow instance URL | (empty) |
| `SERVICENOW_USERNAME` | ServiceNow integration username | (empty) |
| `SERVICENOW_PASSWORD` | ServiceNow integration password | (empty) |
| `SERVICENOW_MOCK` | Use mock ServiceNow adapter | `true` |
| `DEFAULT_TIMEZONE` | Default timezone for shifts | `Asia/Kolkata` |
| `AUTO_ASSIGNMENT_ENABLED` | Enable automatic assignment | `true` |
| `ASSIGNMENT_STRATEGY` | Assignment strategy | `SKILL_PLUS_WORKLOAD` |
| `DRY_RUN_MODE` | Log assignments without executing | `false` |
| `SHADOW_MODE` | Calculate without assigning | `false` |

### Frontend (`frontend/.env.local`)

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

---

## Database

### Run Migrations

```bash
cd backend
alembic upgrade head
```

### Create New Migration

```bash
alembic revision --autogenerate -m "description of change"
```

### Seed Development Data

```bash
python -m scripts.seed_dev
```

---

## Testing

### Backend Tests

```bash
cd backend
pytest tests/ -v --cov=app
```

### Key Test Scenarios

| Test | Description |
|------|-------------|
| One employee | Single eligible employee receives incident |
| Two employees | Least workload strategy selects correct employee |
| Zero employees | Incident goes to unassigned queue, admin notified |
| Duplicate event | Same ServiceNow event processed only once |
| Sync failure | Assignment recorded, retry queued, admin notified |
| Shift boundary | 11:59:59 → morning, 12:00:00 → afternoon |
| Overnight shift | 22:00–06:00 handled correctly |
| Race condition | Concurrent incidents don't all assign to same employee |

---

## API Documentation

FastAPI auto-generates OpenAPI documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Login |
| `GET` | `/api/me` | Current user profile |
| `GET` | `/api/me/work` | My assigned incidents |
| `GET` | `/api/me/shift` | My current shift |
| `GET` | `/api/incidents/{number}` | Incident details |
| `POST` | `/api/incidents/{id}/acknowledge` | Acknowledge assignment |
| `POST` | `/api/incidents/{id}/start` | Start work |
| `POST` | `/api/integrations/servicenow/incidents` | ServiceNow webhook |
| `GET` | `/api/admin/dashboard` | Admin dashboard stats |
| `POST` | `/api/admin/incidents/{id}/assign` | Manual assign |
| `POST` | `/api/admin/incidents/{id}/reassign` | Reassign |

---

## Deployment

See [docs/deployment.md](docs/deployment.md) for full deployment guide.

### Quick Deploy

**Frontend → Vercel:**
1. Connect GitHub repo
2. Set root directory to `frontend`
3. Set `NEXT_PUBLIC_API_URL` environment variable

**Backend → Render:**
1. Create PostgreSQL + Redis services
2. Create Web Service (root: `backend`, start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`)
3. Create Background Worker (start: `celery -A app.workers.celery_app worker`)
4. Set environment variables

---

## Project Structure

```
incidentflow/
├── backend/
│   ├── app/
│   │   ├── api/              # API route handlers
│   │   ├── core/             # Config, database, security
│   │   ├── integrations/     # ServiceNow client & mapper
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   ├── websocket/        # WebSocket manager
│   │   ├── workers/          # Celery tasks
│   │   └── main.py           # FastAPI application
│   ├── alembic/              # Database migrations
│   ├── scripts/              # Seed scripts
│   ├── tests/                # Backend tests
│   └── pyproject.toml
├── frontend/
│   ├── app/                  # Next.js pages (App Router)
│   ├── components/           # React components
│   ├── hooks/                # Custom hooks (TanStack Query)
│   ├── lib/                  # Utilities, API client
│   ├── types/                # TypeScript types
│   └── package.json
├── docs/
│   └── deployment.md
├── docker-compose.yml
└── README.md
```

---

## Roles

| Role | Capabilities |
|------|-------------|
| **Employee** | View dashboard, incidents, shift; acknowledge/start work; update availability |
| **Supervisor** | Employee capabilities + view team, reassign within team |
| **Admin** | Full access: manage employees, shifts, assignments, rules, settings, audit logs |
| **System** | ServiceNow integration, automatic assignment, background processing |

---

## License

Proprietary — Internal use only.
