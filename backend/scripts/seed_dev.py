import asyncio
import os
import sys
from datetime import datetime, date, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.security import get_password_hash
from app.models import (
    Base, User, Team, Employee, Skill, EmployeeSkill, Shift, ShiftAssignment,
    PresenceRecord, Incident, IncidentAssignment, Notification
)

async def seed_dev():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Create Users
        users_data = [
            {"email": "admin@incidentflow.dev", "password": "admin123", "full_name": "Admin User", "role": "ADMIN"},
            {"email": "supervisor@incidentflow.dev", "password": "super123", "full_name": "Supervisor", "role": "SUPERVISOR"},
            {"email": "ravi@incidentflow.dev", "password": "password123", "full_name": "Ravi Kumar", "role": "EMPLOYEE"},
            {"email": "kiran@incidentflow.dev", "password": "password123", "full_name": "Kiran Patel", "role": "EMPLOYEE"},
            {"email": "suresh@incidentflow.dev", "password": "password123", "full_name": "Suresh Reddy", "role": "EMPLOYEE"},
        ]
        
        users_map = {}
        for u in users_data:
            result = await session.execute(select(User).where(User.email == u["email"]))
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    email=u["email"],
                    hashed_password=get_password_hash(u["password"]),
                    full_name=u["full_name"],
                    role=u["role"]
                )
                session.add(user)
                await session.flush()
            users_map[u["email"]] = user

        # Teams
        teams_data = [
            {"name": "MDM L3", "servicenow_group_id": "analytics_mdm_l3"},
            {"name": "Analytics", "servicenow_group_id": "analytics_general"},
            {"name": "Network", "servicenow_group_id": "network_ops"},
        ]
        teams_map = {}
        for t in teams_data:
            result = await session.execute(select(Team).where(Team.name == t["name"]))
            team = result.scalar_one_or_none()
            if not team:
                team = Team(name=t["name"], servicenow_group_id=t["servicenow_group_id"])
                session.add(team)
                await session.flush()
            teams_map[t["name"]] = team

        # Employees
        employees_data = [
            {"user": users_map["ravi@incidentflow.dev"], "team": teams_map["MDM L3"], "code": "EMP001"},
            {"user": users_map["kiran@incidentflow.dev"], "team": teams_map["MDM L3"], "code": "EMP002"},
            {"user": users_map["suresh@incidentflow.dev"], "team": teams_map["MDM L3"], "code": "EMP003"},
        ]
        emps_map = {}
        for e in employees_data:
            result = await session.execute(select(Employee).where(Employee.user_id == e["user"].id))
            emp = result.scalar_one_or_none()
            if not emp:
                emp = Employee(
                    user_id=e["user"].id,
                    team_id=e["team"].id,
                    employee_code=e["code"],
                    availability_status="AVAILABLE",
                    is_present=True
                )
                session.add(emp)
                await session.flush()
            emps_map[e["user"].email] = emp

        # Skills
        skill_names = ["MDM", "SQL", "Linux", "Network", "Python", "ServiceNow"]
        skills_map = {}
        for s in skill_names:
            result = await session.execute(select(Skill).where(Skill.name == s))
            skill = result.scalar_one_or_none()
            if not skill:
                skill = Skill(name=s)
                session.add(skill)
                await session.flush()
            skills_map[s] = skill

        # Employee Skills
        emp_skills_data = [
            ("ravi@incidentflow.dev", ["MDM", "SQL", "Linux"]),
            ("kiran@incidentflow.dev", ["MDM", "SQL"]),
            ("suresh@incidentflow.dev", ["Network", "Linux"]),
        ]
        for email, skills in emp_skills_data:
            emp = emps_map[email]
            for s in skills:
                skill = skills_map[s]
                result = await session.execute(
                    select(EmployeeSkill).where(EmployeeSkill.employee_id == emp.id, EmployeeSkill.skill_id == skill.id)
                )
                if not result.scalar_one_or_none():
                    session.add(EmployeeSkill(employee_id=emp.id, skill_id=skill.id))

        # Shifts
        shifts_data = [
            {"name": "Morning Shift", "start_time": time(9, 0), "end_time": time(12, 0), "is_overnight": False},
            {"name": "Afternoon Shift", "start_time": time(12, 0), "end_time": time(15, 0), "is_overnight": False},
            {"name": "Night Shift", "start_time": time(22, 0), "end_time": time(6, 0), "is_overnight": True},
        ]
        shifts_map = {}
        for sh in shifts_data:
            result = await session.execute(select(Shift).where(Shift.name == sh["name"]))
            shift = result.scalar_one_or_none()
            if not shift:
                shift = Shift(**sh)
                session.add(shift)
                await session.flush()
            shifts_map[sh["name"]] = shift

        # Shift Assignments
        today = date.today()
        morning_shift = shifts_map["Morning Shift"]
        for email in ["ravi@incidentflow.dev", "kiran@incidentflow.dev", "suresh@incidentflow.dev"]:
            emp = emps_map[email]
            result = await session.execute(
                select(ShiftAssignment).where(ShiftAssignment.shift_id == morning_shift.id, ShiftAssignment.employee_id == emp.id, ShiftAssignment.date == today)
            )
            sa_rec = result.scalar_one_or_none()
            if not sa_rec:
                sa_rec = ShiftAssignment(shift_id=morning_shift.id, employee_id=emp.id, date=today)
                session.add(sa_rec)
                await session.flush()

            # Presence
            if email in ["ravi@incidentflow.dev", "kiran@incidentflow.dev"]:
                result = await session.execute(
                    select(PresenceRecord).where(PresenceRecord.employee_id == emp.id, PresenceRecord.date == today)
                )
                if not result.scalar_one_or_none():
                    session.add(PresenceRecord(
                        employee_id=emp.id,
                        shift_assignment_id=sa_rec.id,
                        status="CHECKED_IN",
                        checked_in_at=datetime.now(),
                        date=today
                    ))

        # Incidents
        incidents_data = [
            {"incident_number": "INC1969714", "short_description": "MDM synchronization issue", "priority": "P3", "category": "MDM", "assignment_group": "Analytics – MDM L3", "state": "ASSIGNED"},
            {"incident_number": "INC1969715", "short_description": "Database query performance degradation", "priority": "P2", "category": "Database", "assignment_group": "Analytics – MDM L3", "state": "IN_PROGRESS"},
            {"incident_number": "INC1969716", "short_description": "Network latency in east region", "priority": "P3", "category": "Network", "assignment_group": "Network", "state": "NEW"},
        ]
        incs_map = {}
        for i_data in incidents_data:
            result = await session.execute(select(Incident).where(Incident.incident_number == i_data["incident_number"]))
            inc = result.scalar_one_or_none()
            if not inc:
                inc = Incident(**i_data)
                session.add(inc)
                await session.flush()
            incs_map[i_data["incident_number"]] = inc

        # Assignments
        assignments = [
            {"incident": incs_map["INC1969714"], "employee": emps_map["ravi@incidentflow.dev"], "type": "AUTOMATIC", "status": "ASSIGNED", "started_at": None},
            {"incident": incs_map["INC1969715"], "employee": emps_map["ravi@incidentflow.dev"], "type": "AUTOMATIC", "status": "IN_PROGRESS", "started_at": datetime.now()},
        ]
        for a in assignments:
            result = await session.execute(
                select(IncidentAssignment).where(IncidentAssignment.incident_id == a["incident"].id)
            )
            if not result.scalar_one_or_none():
                session.add(IncidentAssignment(
                    incident_id=a["incident"].id,
                    employee_id=a["employee"].id,
                    assignment_type=a["type"],
                    status=a["status"],
                    started_at=a["started_at"]
                ))
        
        # Notifications
        user_ravi = users_map["ravi@incidentflow.dev"]
        notifs = [
            "New incident assigned: INC1969714",
            "New incident assigned: INC1969715"
        ]
        for n in notifs:
            result = await session.execute(select(Notification).where(Notification.user_id == user_ravi.id, Notification.message == n))
            if not result.scalar_one_or_none():
                session.add(Notification(
                    user_id=user_ravi.id,
                    type="INCIDENT_ASSIGNED",
                    title="Assignment Update",
                    message=n
                ))

        await session.commit()
        print("Dev database seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_dev())
