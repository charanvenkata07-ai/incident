import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.datetime_utils import TZDateTime


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    work_domain: Mapped[str] = mapped_column(String(200), nullable=True)
    servicenow_group_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, onupdate=func.now(), nullable=True)

    employees = relationship("Employee", back_populates="team")
    task_templates = relationship("TaskTemplate", back_populates="team", cascade="all, delete-orphan")
