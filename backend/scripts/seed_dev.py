import asyncio
import os
import sys
from datetime import datetime, date, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import engine, async_session_maker
from app.core.security import get_password_hash
from app.models import (
    Base, User, Team, Employee, Skill, EmployeeSkill, Shift, ShiftAssignment,
    PresenceRecord, Incident, IncidentAssignment, Notification
)

RECIPIENT_EMAILS = [
    "charanvenkata07@gmail.com",
    "charanvenkata975@gmail.com",
    "ugjggug26@gmail.com",
    "venkatacharan927@gmail.com",
    "bnbbandi582@gmail.com",
    "editzcharan827@gmail.com",
    "pegadagowtham15@gmail.com",
    "gbo33369@gmail.com",
    "pvcharan510@gmail.com",
    "charanv668@gmail.com",
    "charanvenkata53@gmail.com",
]

async def seed_dev():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # 1. System Administrative Users
        users_data = [
            {"email": "pvcharan975@gmail.com", "password": "pvcharan12345PV", "full_name": "Administrator (pvcharan975)", "role": "ADMIN"},
            {"email": "admin@incidentflow.dev", "password": "pvcharan12345PV", "full_name": "Admin User", "role": "ADMIN"},
            {"email": "supervisor@incidentflow.dev", "password": "pvcharan12345PV", "full_name": "Supervisor", "role": "SUPERVISOR"},
            {"email": "ravi@incidentflow.dev", "password": "pvcharan12345", "full_name": "Ravi Kumar", "role": "EMPLOYEE"},
            {"email": "kiran@incidentflow.dev", "password": "pvcharan12345", "full_name": "Kiran Patel", "role": "EMPLOYEE"},
            {"email": "suresh@incidentflow.dev", "password": "pvcharan12345", "full_name": "Suresh Reddy", "role": "EMPLOYEE"},
        ]

        # Add the requested development recipient list as real test employees
        for idx, email in enumerate(RECIPIENT_EMAILS, start=1):
            name_part = email.split('@')[0].replace('.', ' ').capitalize()
            users_data.append({
                "email": email,
                "password": "pvcharan12345",
                "full_name": f"Engineer {name_part}",
                "role": "EMPLOYEE"
            })

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

        # 2. Teams
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

        # 3. Employees
        emps_map = {}
        # Core demo team
        demo_emps = [
            {"email": "ravi@incidentflow.dev", "team": teams_map["MDM L3"], "code": "EMP001"},
            {"email": "kiran@incidentflow.dev", "team": teams_map["MDM L3"], "code": "EMP002"},
            {"email": "suresh@incidentflow.dev", "team": teams_map["MDM L3"], "code": "EMP003"},
        ]
        # Attach additional recipient users to MDM L3 or Analytics
        for idx, email in enumerate(RECIPIENT_EMAILS, start=4):
            demo_emps.append({
                "email": email,
                "team": teams_map["MDM L3"] if idx % 2 == 0 else teams_map["Analytics"],
                "code": f"EMP{idx:03d}"
            })

        for e in demo_emps:
            usr = users_map[e["email"]]
            result = await session.execute(select(Employee).where(Employee.user_id == usr.id))
            emp = result.scalar_one_or_none()
            if not emp:
                emp = Employee(
                    user_id=usr.id,
                    team_id=e["team"].id,
                    employee_code=e["code"],
                    availability_status="AVAILABLE",
                    is_present=True
                )
                session.add(emp)
                await session.flush()
            emps_map[e["email"]] = emp

        # 4. Skills
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

        # Attach skills to employees
        emp_skills_data = [
            ("ravi@incidentflow.dev", ["MDM", "SQL", "Linux"]),
            ("kiran@incidentflow.dev", ["MDM", "SQL"]),
            ("suresh@incidentflow.dev", ["Network", "Linux"]),
        ]
        for email, skills in emp_skills_data:
            emp = emps_map[email]
            for s in skills:
                sk = skills_map[s]
                result = await session.execute(
                    select(EmployeeSkill).where(EmployeeSkill.employee_id == emp.id, EmployeeSkill.skill_id == sk.id)
                )
                if not result.scalar_one_or_none():
                    session.add(EmployeeSkill(employee_id=emp.id, skill_id=sk.id))

        # 5. Shifts
        shifts_data = [
            {"name": "Morning Shift", "start_time": time(9, 0), "end_time": time(12, 0), "is_overnight": False},
            {"name": "Afternoon Shift", "start_time": time(12, 0), "end_time": time(15, 0), "is_overnight": False},
            {"name": "Evening Shift", "start_time": time(15, 0), "end_time": time(22, 0), "is_overnight": False},
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

        # 6. Shift Assignments & Presence for today
        today = date.today()
        for s_name in ["Morning Shift", "Afternoon Shift", "Evening Shift", "Night Shift"]:
            curr_shift = shifts_map[s_name]
            for email in ["ravi@incidentflow.dev", "kiran@incidentflow.dev", "suresh@incidentflow.dev"]:
                emp = emps_map[email]
                result = await session.execute(
                    select(ShiftAssignment).where(
                        ShiftAssignment.shift_id == curr_shift.id,
                        ShiftAssignment.employee_id == emp.id,
                        ShiftAssignment.date == today
                    )
                )
                sa_rec = result.scalar_one_or_none()
                if not sa_rec:
                    sa_rec = ShiftAssignment(shift_id=curr_shift.id, employee_id=emp.id, date=today)
                    session.add(sa_rec)
                    await session.flush()

            if email in ["ravi@incidentflow.dev", "kiran@incidentflow.dev"]:
                pres_res = await session.execute(
                    select(PresenceRecord).where(PresenceRecord.employee_id == emp.id, PresenceRecord.date == today)
                )
                if not pres_res.scalar_one_or_none():
                    session.add(PresenceRecord(
                        employee_id=emp.id,
                        shift_assignment_id=sa_rec.id,
                        status="CHECKED_IN",
                        checked_in_at=datetime.now(),
                        date=today
                    ))

        # 7. Demo Incidents
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

        # 8. Assignments
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

        await session.commit()
        print("Dev database seeded with core employees & test recipients successfully!")

if __name__ == "__main__":
    asyncio.run(seed_dev())
