import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    servicenow_sys_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=True, index=True)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(5), default="P4")
    impact: Mapped[str] = mapped_column(String(20), nullable=True)
    urgency: Mapped[str] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[str] = mapped_column(String(100), nullable=True)
    assignment_group: Mapped[str] = mapped_column(String(200), nullable=True)
    assigned_to: Mapped[str] = mapped_column(String(200), nullable=True)
    caller: Mapped[str] = mapped_column(String(200), nullable=True)
    location: Mapped[str] = mapped_column(String(200), nullable=True)
    configuration_item: Mapped[str] = mapped_column(String(200), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="NEW")
    work_notes: Mapped[str] = mapped_column(Text, nullable=True)
    additional_comments: Mapped[str] = mapped_column(Text, nullable=True)
    work_instructions: Mapped[str] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    servicenow_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    assignments = relationship("IncidentAssignment", back_populates="incident")
    required_skills = relationship("IncidentRequiredSkill", back_populates="incident")

class IncidentRequiredSkill(Base):
    __tablename__ = "incident_required_skills"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id"))
    skill_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("skills.id"))

    __table_args__ = (
        UniqueConstraint('incident_id', 'skill_id'),
    )

    incident = relationship("Incident", back_populates="required_skills")
