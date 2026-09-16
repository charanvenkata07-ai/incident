import uuid
from datetime import datetime, date, time
from sqlalchemy import String, Boolean, DateTime, Date, Time, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    is_overnight: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    assignments = relationship("ShiftAssignment", back_populates="shift")

class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shift_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("shifts.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint('shift_id', 'employee_id', 'date'),
        Index('ix_shift_assignments_date_shift', 'date', 'shift_id'),
    )

    shift = relationship("Shift", back_populates="assignments")
    employee = relationship("Employee", back_populates="shift_assignments")
