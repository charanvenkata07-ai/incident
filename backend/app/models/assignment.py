import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class IncidentAssignment(Base):
    __tablename__ = "incident_assignments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ASSIGNED")
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('ix_inc_assign_inc_active', 'incident_id', 'is_active'),
        Index('ix_inc_assign_emp_active', 'employee_id', 'is_active'),
    )

    incident = relationship("Incident", back_populates="assignments")
    employee = relationship("Employee", back_populates="incident_assignments")
    assigner = relationship("User")
