import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.integrations.servicenow.mapper import ServiceNowMapper

class IncidentService:
    """
    Manages incident persistence, deduplication across ServiceNow sys_ids,
    and querying for employee work assignments.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.mapper = ServiceNowMapper()

    async def create_or_update_from_servicenow(self, payload: ServiceNowIncidentPayload) -> tuple[Incident, bool]:
        """
        Idempotent ingest: finds existing incident by sys_id or number.
        Updates if found; creates if new.
        Returns: (incident, is_new)
        """
        existing = await self._find_existing(payload)
        if existing:
            updated = await self._update_incident(existing, payload)
            return updated, False
        
        created = await self._create_incident(payload)
        return created, True

    async def _find_existing(self, payload) -> Incident | None:
        payload_dict = payload.model_dump() if hasattr(payload, "model_dump") else (payload.dict() if hasattr(payload, "dict") else dict(payload))
        sys_id = payload_dict.get("sys_id")
        number = payload_dict.get("number") or payload_dict.get("incident_number")

        if sys_id:
            stmt = select(Incident).where(Incident.servicenow_sys_id == sys_id)
            res = await self.db.execute(stmt)
            match = res.scalar_one_or_none()
            if match:
                return match

        if number:
            stmt = select(Incident).where(Incident.incident_number == number)
            res = await self.db.execute(stmt)
            match = res.scalar_one_or_none()
            if match:
                return match

        return None

    async def _update_incident(self, existing: Incident, payload) -> Incident:
        payload_dict = payload.model_dump() if hasattr(payload, "model_dump") else (payload.dict() if hasattr(payload, "dict") else dict(payload))
        mapped = self.mapper.to_incident(payload_dict)
        
        # Only update mutable fields
        if mapped.get("short_description"):
            existing.short_description = mapped["short_description"]
        if mapped.get("description"):
            existing.description = mapped["description"]
        if mapped.get("priority"):
            existing.priority = mapped["priority"]
        if mapped.get("impact"):
            existing.impact = mapped["impact"]
        if mapped.get("urgency"):
            existing.urgency = mapped["urgency"]
        if mapped.get("category"):
            existing.category = mapped["category"]
        if mapped.get("subcategory"):
            existing.subcategory = mapped["subcategory"]
        if mapped.get("assignment_group"):
            existing.assignment_group = mapped["assignment_group"]
        if mapped.get("state"):
            existing.state = mapped["state"]
        if mapped.get("work_instructions"):
            existing.work_instructions = mapped["work_instructions"]
        elif not existing.work_instructions and existing.assignment_group:
            existing.work_instructions = await self._resolve_task_instructions(existing.assignment_group)

        if mapped.get("work_notes"):
            existing.work_notes = mapped["work_notes"]
        if mapped.get("additional_comments"):
            existing.additional_comments = mapped["additional_comments"]
        
        existing.updated_at = datetime.now(timezone.utc)
        existing.servicenow_updated_at = datetime.now(timezone.utc)
        
        await self.db.flush()
        return existing

    async def _resolve_task_instructions(self, assignment_group: str) -> str | None:
        if not assignment_group:
            return None
        from app.models.team import Team
        from app.models.task_template import TaskTemplate
        import random

        team_res = await self.db.execute(
            select(Team).where(
                (Team.name == assignment_group) |
                (Team.servicenow_group_id == assignment_group) |
                (Team.name.ilike(f"%{assignment_group}%"))
            )
        )
        team = team_res.scalar_one_or_none()
        if team:
            tasks_res = await self.db.execute(
                select(TaskTemplate).where(
                    TaskTemplate.team_id == team.id,
                    TaskTemplate.is_active == True
                )
            )
            tasks = tasks_res.scalars().all()
            if tasks:
                chosen = random.choice(tasks)
                return f"{chosen.title}: {chosen.description}" if chosen.description else chosen.title
        return None

    async def _create_incident(self, payload) -> Incident:
        payload_dict = payload.model_dump() if hasattr(payload, "model_dump") else (payload.dict() if hasattr(payload, "dict") else dict(payload))
        mapped = self.mapper.to_incident(payload_dict)
        
        # Requirement: If incident has no explicit work instructions from ServiceNow,
        # select an appropriate task template from the group's Admin-managed Task Catalog.
        work_instr = mapped.get("work_instructions")
        if not work_instr and mapped.get("assignment_group"):
            work_instr = await self._resolve_task_instructions(mapped["assignment_group"])

        incident = Incident(
            id=uuid.uuid4(),
            incident_number=mapped.get("incident_number") or f"INC{uuid.uuid4().hex[:7].upper()}",
            servicenow_sys_id=mapped.get("servicenow_sys_id"),
            short_description=mapped.get("short_description") or "Untitled Incident",
            description=mapped.get("description"),
            priority=mapped.get("priority") or "P3",
            impact=mapped.get("impact"),
            urgency=mapped.get("urgency"),
            category=mapped.get("category"),
            subcategory=mapped.get("subcategory"),
            assignment_group=mapped.get("assignment_group"),
            assigned_to=mapped.get("assigned_to"),
            caller=mapped.get("caller"),
            location=mapped.get("location"),
            configuration_item=mapped.get("configuration_item"),
            state=mapped.get("state") or "NEW",
            work_notes=mapped.get("work_notes"),
            additional_comments=mapped.get("additional_comments"),
            work_instructions=work_instr,
            opened_at=mapped.get("opened_at") or datetime.now(timezone.utc),
            sync_status="SYNCED"
        )
        self.db.add(incident)
        await self.db.flush()
        return incident

    async def get_incident_by_number(self, incident_number: str) -> Incident | None:
        stmt = select(Incident).where(Incident.incident_number == incident_number)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_employee_incidents(self, employee_id: uuid.UUID, status_filter: str | None = None) -> list[Incident]:
        stmt = (
            select(Incident)
            .join(IncidentAssignment, Incident.id == IncidentAssignment.incident_id)
            .where(IncidentAssignment.employee_id == employee_id, IncidentAssignment.is_active == True)
        )
        if status_filter and status_filter.upper() != "ALL":
            stmt = stmt.where(IncidentAssignment.status == status_filter.upper())
        
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_all_incidents(self, filters: dict = None, page: int = 1, per_page: int = 20) -> tuple[list[Incident], int]:
        stmt = select(Incident)
        if filters:
            if filters.get("priority"):
                stmt = stmt.where(Incident.priority == filters["priority"])
            if filters.get("state"):
                stmt = stmt.where(Incident.state == filters["state"])
            if filters.get("assignment_group"):
                stmt = stmt.where(Incident.assignment_group == filters["assignment_group"])
        
        count_stmt = select(func.count(Incident.id))
        total_res = await self.db.execute(count_stmt)
        total = total_res.scalar() or 0

        stmt = stmt.order_by(desc(Incident.created_at)).offset((page - 1) * per_page).limit(per_page)
        res = await self.db.execute(stmt)
        return list(res.scalars().all()), total
