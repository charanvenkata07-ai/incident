import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Integer, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class IncidentAssignment(Base):
    __tablename__ = "incident_assignments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ASSIGNED")
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scheduled_shift_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    assignment_cycle_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("assignment_cycles.id", ondelete="CASCADE"), nullable=True, index=True)
    previous_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    reassigned_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rotation_cycle: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rotation_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_inc_assign_inc_active', 'incident_id', 'is_active'),
        Index('ix_inc_assign_emp_active', 'employee_id', 'is_active'),
        Index('ix_inc_assign_team_rot', 'team_id', 'rotation_cycle', 'rotation_position'),
        Index('uq_incident_emp_cycle', 'incident_id', 'employee_id', 'cycle_number', unique=True),
        Index('uq_cycle_emp', 'assignment_cycle_id', 'employee_id', unique=True),
        Index(
            'uq_active_incident_emp_assignment',
            'incident_id',
            'employee_id',
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true")
        ),
    )

    incident = relationship("Incident", back_populates="assignments")
    employee = relationship("Employee", foreign_keys=[employee_id], back_populates="incident_assignments")
    previous_employee = relationship("Employee", foreign_keys=[previous_employee_id])
    assigner = relationship("User")
    team = relationship("Team")
    cycle = relationship("AssignmentCycle", foreign_keys=[assignment_cycle_id], back_populates="assignments")

