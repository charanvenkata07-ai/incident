import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class PresenceRecord(Base):
    __tablename__ = "presence_records"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    shift_assignment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("shift_assignments.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index('ix_presence_records_emp_date', 'employee_id', 'date'),
    )
