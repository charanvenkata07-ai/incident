import uuid
from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    employees = relationship("EmployeeSkill", back_populates="skill")

class EmployeeSkill(Base):
    __tablename__ = "employee_skills"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    skill_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("skills.id"), nullable=False)
    proficiency_level: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint('employee_id', 'skill_id'),
    )

    employee = relationship("Employee", back_populates="skills")
    skill = relationship("Skill", back_populates="employees")
