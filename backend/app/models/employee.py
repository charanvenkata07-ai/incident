import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    employee_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=True)
    availability_status: Mapped[str] = mapped_column(String(20), default="OFFLINE")
    is_present: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User", back_populates="employee")
    team = relationship("Team", back_populates="employees")
    skills = relationship("EmployeeSkill", back_populates="employee")
    shift_assignments = relationship("ShiftAssignment", back_populates="employee")
    incident_assignments = relationship("IncidentAssignment", back_populates="employee")
