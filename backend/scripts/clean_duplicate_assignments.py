import asyncio
import uuid
import structlog
from sqlalchemy import select, delete, text, func
from app.core.database import async_session_maker, engine
from app.models.assignment import IncidentAssignment
from app.models.incident import Incident
from app.models.integration import IntegrationEvent
from app.models.notification import Notification

logger = structlog.get_logger()

DUPLICATE_ASSIGNMENT_IDS = [
    uuid.UUID("ab1c85c7-0283-4340-90c1-275c25aef46c"),
    uuid.UUID("141c3600-422e-4f2d-9335-7d2514606d21"),
    uuid.UUID("5c0ed9ae-c050-4d7a-add1-9f19ba598fea"),
]

async def migrate_and_clean():
    async with engine.begin() as conn:
        dialect = engine.dialect.name
        logger.info("migration.start", dialect=dialect)

        if dialect == "sqlite":
            # Add cycle_number to incident_assignments
            res = await conn.execute(text("PRAGMA table_info(incident_assignments)"))
            cols = [row[1] for row in res.fetchall()]
            if "cycle_number" not in cols:
                logger.info("adding_column.cycle_number")
                await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN cycle_number INTEGER NOT NULL DEFAULT 1"))
            if "assignment_cycle_id" not in cols:
                logger.info("adding_column.assignment_cycle_id")
                await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN assignment_cycle_id VARCHAR(100)"))

            # Add current_cycle to incidents
            res = await conn.execute(text("PRAGMA table_info(incidents)"))
            cols = [row[1] for row in res.fetchall()]
            if "current_cycle" not in cols:
                logger.info("adding_column.current_cycle")
                await conn.execute(text("ALTER TABLE incidents ADD COLUMN current_cycle INTEGER NOT NULL DEFAULT 1"))

            # Add idempotency_key to integration_events
            res = await conn.execute(text("PRAGMA table_info(integration_events)"))
            cols = [row[1] for row in res.fetchall()]
            if "idempotency_key" not in cols:
                logger.info("adding_column.idempotency_key")
                await conn.execute(text("ALTER TABLE integration_events ADD COLUMN idempotency_key VARCHAR(255)"))

            # Create assignment_cycles table if not exists
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assignment_cycles (
                    id VARCHAR(100) PRIMARY KEY,
                    incident_id CHAR(36) NOT NULL,
                    team_id CHAR(36) NOT NULL,
                    cycle_number INTEGER NOT NULL DEFAULT 1,
                    status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
                    total_members INTEGER NOT NULL DEFAULT 10,
                    assigned_count INTEGER NOT NULL DEFAULT 0,
                    idempotency_key VARCHAR(255) UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
                    FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
                )
            """))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_cycle_num ON assignment_cycles (incident_id, cycle_number)"))

            # Clean duplicate assignment rows BEFORE creating unique index
            for d_id in DUPLICATE_ASSIGNMENT_IDS:
                hex_id = d_id.hex
                await conn.execute(text("DELETE FROM incident_assignments WHERE id = :id OR replace(id, '-', '') = :hex_id"), {"id": str(d_id), "hex_id": hex_id})

            # Drop old single-owner index that prevented group assignments
            await conn.execute(text("DROP INDEX IF EXISTS uq_active_incident_assignment"))

            if "rotation_cycle" not in cols:
                logger.info("adding_column.rotation_cycle")
                await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN rotation_cycle INTEGER"))
            if "rotation_position" not in cols:
                logger.info("adding_column.rotation_position")
                await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN rotation_position INTEGER"))
            if "source_event_id" not in cols:
                logger.info("adding_column.source_event_id")
                await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN source_event_id VARCHAR(255)"))

            # Create team_rotations table if not exists
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS team_rotations (
                    id CHAR(36) PRIMARY KEY,
                    team_id CHAR(36) NOT NULL UNIQUE,
                    current_position INTEGER NOT NULL DEFAULT 1,
                    cycle_number INTEGER NOT NULL DEFAULT 1,
                    last_assigned_employee_id CHAR(36),
                    last_incident_id CHAR(36),
                    last_idempotency_key VARCHAR(255),
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
                    FOREIGN KEY(last_assigned_employee_id) REFERENCES employees(id) ON DELETE SET NULL,
                    FOREIGN KEY(last_incident_id) REFERENCES incidents(id) ON DELETE SET NULL
                )
            """))

            # Create partial/unique indexes
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_emp_cycle ON incident_assignments (incident_id, employee_id, cycle_number)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cycle_emp ON incident_assignments (assignment_cycle_id, employee_id)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_active_incident_emp_assignment ON incident_assignments (incident_id, employee_id) WHERE is_active = 1"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_inc_assign_team_rot ON incident_assignments (team_id, rotation_cycle, rotation_position)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_assignment_user_type ON notifications (assignment_id, user_id, type) WHERE assignment_id IS NOT NULL"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_integration_event_idempotency ON integration_events (idempotency_key) WHERE idempotency_key IS NOT NULL"))

        elif dialect == "postgresql":
            await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN IF NOT EXISTS cycle_number INTEGER NOT NULL DEFAULT 1"))
            await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN IF NOT EXISTS assignment_cycle_id VARCHAR(100)"))
            await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN IF NOT EXISTS rotation_cycle INTEGER"))
            await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN IF NOT EXISTS rotation_position INTEGER"))
            await conn.execute(text("ALTER TABLE incident_assignments ADD COLUMN IF NOT EXISTS source_event_id VARCHAR(255)"))
            await conn.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS current_cycle INTEGER NOT NULL DEFAULT 1"))
            await conn.execute(text("ALTER TABLE integration_events ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(255)"))

            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS assignment_cycles (
                    id VARCHAR(100) PRIMARY KEY,
                    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                    cycle_number INTEGER NOT NULL DEFAULT 1,
                    status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
                    total_members INTEGER NOT NULL DEFAULT 10,
                    assigned_count INTEGER NOT NULL DEFAULT 0,
                    idempotency_key VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    completed_at TIMESTAMP WITH TIME ZONE
                )
            """))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_cycle_num ON assignment_cycles (incident_id, cycle_number)"))

            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS team_rotations (
                    id UUID PRIMARY KEY,
                    team_id UUID NOT NULL UNIQUE REFERENCES teams(id) ON DELETE CASCADE,
                    current_position INTEGER NOT NULL DEFAULT 1,
                    cycle_number INTEGER NOT NULL DEFAULT 1,
                    last_assigned_employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
                    last_incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
                    last_idempotency_key VARCHAR(255),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            for d_id in DUPLICATE_ASSIGNMENT_IDS:
                await conn.execute(text("DELETE FROM incident_assignments WHERE id = :id"), {"id": str(d_id)})

            await conn.execute(text("DROP INDEX IF EXISTS uq_active_incident_assignment"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_emp_cycle ON incident_assignments (incident_id, employee_id, cycle_number)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cycle_emp ON incident_assignments (assignment_cycle_id, employee_id)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_active_incident_emp_assignment ON incident_assignments (incident_id, employee_id) WHERE is_active = true"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_inc_assign_team_rot ON incident_assignments (team_id, rotation_cycle, rotation_position)"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_notif_assignment_user_type ON notifications (assignment_id, user_id, type) WHERE assignment_id IS NOT NULL"))
            await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_integration_event_idempotency ON integration_events (idempotency_key) WHERE idempotency_key IS NOT NULL"))

    logger.info("migration_and_cleanup_complete")

if __name__ == "__main__":
    asyncio.run(migrate_and_clean())

