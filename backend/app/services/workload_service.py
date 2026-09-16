from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from sqlalchemy import select, func
from app.models.assignment import IncidentAssignment

class WorkloadService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_workloads(self, employee_ids: list[UUID]) -> dict[UUID, int]:
        result = await self.db.execute(
            select(IncidentAssignment.employee_id, func.count(IncidentAssignment.id))
            .where(
                IncidentAssignment.employee_id.in_(employee_ids),
                IncidentAssignment.is_active == True,
                IncidentAssignment.status.in_(['ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS'])
            )
            .group_by(IncidentAssignment.employee_id)
        )
        counts = {row[0]: row[1] for row in result.all()}
        return {eid: counts.get(eid, 0) for eid in employee_ids}

    async def get_detailed_workload(self, employee_id: UUID) -> dict:
        return {"total": 0, "p1": 0, "p2": 0, "p3": 0, "p4": 0}
