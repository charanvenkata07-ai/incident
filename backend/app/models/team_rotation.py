import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TeamRotation(Base):
    __tablename__ = "team_rotations"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    current_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_assigned_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    last_incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    last_idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    team = relationship("Team")
    last_assigned_employee = relationship("Employee", foreign_keys=[last_assigned_employee_id])
    last_incident = relationship("Incident", foreign_keys=[last_incident_id])
