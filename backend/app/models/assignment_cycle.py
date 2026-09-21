import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Integer, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class AssignmentCycle(Base):
    __tablename__ = "assignment_cycles"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="IN_PROGRESS")
    total_members: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    assigned_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('uq_incident_cycle_num', 'incident_id', 'cycle_number', unique=True),
        Index('ix_assignment_cycles_team', 'team_id'),
    )

    incident = relationship("Incident")
    team = relationship("Team")
    assignments = relationship("IncidentAssignment", foreign_keys="[IncidentAssignment.assignment_cycle_id]")
