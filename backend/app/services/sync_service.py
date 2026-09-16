from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import Incident
from app.models.employee import Employee
from app.models.integration import SyncFailure
from app.integrations.servicenow.client import ServiceNowClient

class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = ServiceNowClient("url", "user", "pass")

    async def sync_assignment_to_servicenow(self, incident: Incident, employee: Employee):
        try:
            await self.client.update_assignment(incident.servicenow_sys_id, employee.user.full_name)
            incident.sync_status = 'SYNCED'
        except Exception as e:
            incident.sync_status = 'SYNC_FAILED'
            await self._create_sync_failure(incident, 'UPDATE_ASSIGNMENT', str(e))

    async def sync_status_to_servicenow(self, incident: Incident, new_state: str):
        pass

    async def handle_servicenow_update(self, payload) -> bool:
        return True

    async def retry_failed_syncs(self):
        pass

    async def _create_sync_failure(self, incident, operation, error):
        fail = SyncFailure(incident_id=incident.id, operation=operation, error_message=error, status='PENDING')
        self.db.add(fail)
        await self.db.flush()
