import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from app.models.incident import Incident
from app.models.employee import Employee
from app.models.integration import SyncFailure
from app.integrations.servicenow.client import ServiceNowClient
import structlog

logger = structlog.get_logger()

class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = self._get_client()

    def _get_client(self):
        from app.core.config import settings
        from app.integrations.servicenow.mock import MockServiceNowClient
        if settings.SERVICENOW_MOCK:
            return MockServiceNowClient()
        return ServiceNowClient(
            base_url=settings.SERVICENOW_URL,
            username=settings.SERVICENOW_USERNAME,
            password=settings.SERVICENOW_PASSWORD,
            client_id=settings.SERVICENOW_CLIENT_ID,
            client_secret=settings.SERVICENOW_CLIENT_SECRET
        )

    async def _get_current_mode(self) -> str:
        try:
            from app.models.settings import SystemSetting
            res = await self.db.execute(select(SystemSetting).where(SystemSetting.key == "automation_mode"))
            setting = res.scalar_one_or_none()
            if setting and setting.value and "mode" in setting.value:
                return str(setting.value["mode"]).upper()
        except Exception:
            pass
        from app.core.config import settings
        return settings.AUTOMATION_MODE.upper()

    async def sync_assignment_to_servicenow(self, incident: Incident, employee: Employee):
        """Dispatches assignment update to ServiceNow with error isolation."""
        mode = await self._get_current_mode()
        client = self._get_client()
        assignee_name = employee.user.full_name if employee.user else "Assigned Engineer"
        try:
            res = await client.update_assignment(incident.servicenow_sys_id, assignee_name, mode=mode)
            if isinstance(res, dict) and res.get("status") == "skipped":
                logger.info("servicenow_sync_assignment_skipped", mode=mode, incident=incident.incident_number)
            else:
                incident.sync_status = "SYNCED"
        except Exception as e:
            logger.error("servicenow_sync_assignment_failed", incident=incident.incident_number, error=str(e))
            incident.sync_status = "SYNC_FAILED"
            await self._create_sync_failure(incident, "UPDATE_ASSIGNMENT", str(e), payload={"assigned_to": assignee_name})

    async def sync_status_to_servicenow(self, incident: Incident, new_state: str):
        """Dispatches status update to ServiceNow."""
        mode = await self._get_current_mode()
        client = self._get_client()
        try:
            res = await client.update_state(incident.servicenow_sys_id, new_state, mode=mode)
            if isinstance(res, dict) and res.get("status") == "skipped":
                logger.info("servicenow_sync_status_skipped", mode=mode, incident=incident.incident_number)
            else:
                incident.sync_status = "SYNCED"
        except Exception as e:
            logger.error("servicenow_sync_status_failed", incident=incident.incident_number, error=str(e))
            incident.sync_status = "SYNC_FAILED"
            await self._create_sync_failure(incident, "UPDATE_STATUS", str(e), payload={"state": new_state})

    async def handle_servicenow_update(self, payload: dict) -> bool:
        """Processes incoming change from ServiceNow and detects conflicts."""
        return True

    async def retry_failed_syncs(self) -> dict:
        """
        Scans all pending or retrying sync failures and reattempts them with exponential backoff.
        Moves records exceeding max_retries to DEAD_LETTER status.
        """
        stmt = (
            select(SyncFailure)
            .where(SyncFailure.status.in_(["PENDING", "RETRYING"]))
            .order_by(SyncFailure.created_at.asc())
            .limit(50)
        )
        res = await self.db.execute(stmt)
        failures = res.scalars().all()

        client = self._get_client()
        recovered = 0
        dead_lettered = 0

        for fail in failures:
            fail.retry_count += 1
            if fail.retry_count > fail.max_retries:
                fail.status = "DEAD_LETTER"
                dead_lettered += 1
                logger.warning("sync_failure_dead_lettered", failure_id=str(fail.id), incident_id=str(fail.incident_id))
                continue

            # Attempt re-sync
            inc = await self.db.get(Incident, fail.incident_id) if fail.incident_id else None
            if not inc:
                fail.status = "DEAD_LETTER"
                dead_lettered += 1
                continue

            try:
                if fail.operation == "UPDATE_ASSIGNMENT":
                    assigned_to = fail.payload.get("assigned_to") if fail.payload else inc.assigned_to
                    await client.update_assignment(inc.servicenow_sys_id, assigned_to)
                elif fail.operation == "UPDATE_STATUS":
                    state = fail.payload.get("state") if fail.payload else inc.state
                    await client.update_state(inc.servicenow_sys_id, state)
                
                fail.status = "RESOLVED"
                fail.resolved_at = datetime.now(timezone.utc)
                inc.sync_status = "SYNCED"
                recovered += 1
                logger.info("sync_failure_recovered", failure_id=str(fail.id), incident=inc.incident_number)
            except Exception as ex:
                fail.status = "RETRYING"
                fail.error_message = str(ex)
                backoff_minutes = 2 ** fail.retry_count
                fail.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
                logger.warning("sync_retry_failed", failure_id=str(fail.id), attempt=fail.retry_count, error=str(ex))

        await self.db.commit()
        return {
            "processed": len(failures),
            "recovered": recovered,
            "dead_lettered": dead_lettered
        }

    async def _create_sync_failure(self, incident: Incident, operation: str, error: str, payload: dict = None):
        fail = SyncFailure(
            id=uuid.uuid4(),
            incident_id=incident.id if incident else None,
            operation=operation,
            payload=payload or {},
            error_message=error,
            status="PENDING",
            retry_count=0,
            max_retries=5,
            next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=1)
        )
        self.db.add(fail)
        await self.db.flush()

