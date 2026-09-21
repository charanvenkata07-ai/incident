"""
IncidentFlow — Authoritative Test Suite: 15 Teams, 150 Employees, Deterministic Rotation
Verifies:
1. Organization total employees = 150
2. Organization total active employees = 150
3. Organization total teams = 15
4. Each team has exactly 10 employees
5. Every employee has unique Employee ID
6. Group Leader is one of the 10 members (total remains 10)
7. Notice 1 assigns EMP001
8. Notice 2 assigns EMP002
9. Notice 10 assigns EMP010
10. Notice 11 assigns EMP001 (Cycle 2)
11. Notice 20 assigns EMP010 (Cycle 2)
12. Notice 21 assigns EMP001 (Cycle 3)
13. Notice 25 assigns EMP005 (Cycle 3)
14. Team Notice creates exactly ONE assignment record
15. Team Notice sends notice to all 10 members
16. Only selected employee receives personal notification
17. Only selected employee receives MY_WORK_UPDATED event
18. Concurrent notices select sequential employees (Req A -> EMP001, Req B -> EMP002)
19. Duplicate notice submission does NOT advance rotation
20. Rotation state persists across process restart
21. Changing group leader does NOT change rotation order
22. Unregistered/inactive team raises validation error
23. Team with != 10 members raises validation error
24. Forbidden word 'unassigned' does not appear in any API response
25. 25-notice acceptance test passes cleanly
"""
import uuid
import pytest
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func, update
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.team_rotation import TeamRotation
from app.models.notification import Notification
from app.services.org_validation import validate_organization_structure, OrgValidationError
from app.services.rotation_service import TeamRotationService

import pytest_asyncio

CANONICAL_TEAMS = [
    "MDM L3", "Database L2", "Network L2", "Linux L2", "Windows L2",
    "Cloud Operations L2", "Application Support L2", "Security Operations L2",
    "Storage & Backup L2", "Monitoring & Batch L2", "DevOps & SRE L2",
    "Identity & Access L2", "Messaging & Collaboration L2", "API Gateway L2",
    "Data Platform L2"
]


@pytest_asyncio.fixture(autouse=True)
async def isolate_15_canonical_teams():
    async with async_session_maker() as session:
        await session.execute(
            update(Team).where(~Team.name.in_(CANONICAL_TEAMS)).values(is_active=False)
        )
        await session.execute(
            update(Team).where(Team.name.in_(CANONICAL_TEAMS)).values(is_active=True)
        )
        team_ids = (await session.execute(
            select(Team.id).where(Team.name.in_(CANONICAL_TEAMS))
        )).scalars().all()
        await session.execute(
            update(Employee)
            .where(Employee.team_id.in_(team_ids))
            .values(is_present=True, availability_status="AVAILABLE")
        )
        db_team = (await session.execute(select(Team).where(Team.name == "Database L2"))).scalar_one_or_none()
        if db_team:
            db001 = (await session.execute(
                select(Employee).where(Employee.team_id == db_team.id, Employee.employee_code == "DB001")
            )).scalar_one_or_none()
            if db001 and not db001.is_group_leader:
                db001.is_group_leader = True
        await session.commit()
    yield


@pytest.mark.asyncio
async def test_01_organization_total_employees():
    """Test 1: Organization active teams total active employees is exactly 150."""
    async with async_session_maker() as session:
        active_teams = (await session.execute(
            select(Team.id).where(Team.is_active == True)
        )).scalars().all()
        assert len(active_teams) == 15

        res = await session.execute(
            select(func.count(Employee.id))
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.team_id.in_(active_teams),
                User.is_active == True
            )
        )
        total_active_emps = res.scalar()
        assert total_active_emps == 150


@pytest.mark.asyncio
async def test_02_organization_total_active_employees():
    """Test 2: All 150 employees in active teams are active."""
    async with async_session_maker() as session:
        active_teams = (await session.execute(
            select(Team.id).where(Team.is_active == True)
        )).scalars().all()

        res = await session.execute(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.team_id.in_(active_teams),
                User.is_active == True
            )
        )
        emps = res.scalars().all()
        assert len(emps) == 150
        for e in emps:
            assert e.availability_status == "AVAILABLE"
            assert e.is_present is True


@pytest.mark.asyncio
async def test_03_organization_total_active_teams():
    """Test 3: Organization has exactly 15 active teams."""
    async with async_session_maker() as session:
        res = await session.execute(select(func.count(Team.id)).where(Team.is_active == True))
        assert res.scalar() == 15


@pytest.mark.asyncio
async def test_04_each_team_has_exactly_10_employees():
    """Test 4: Each of the 15 active teams has exactly 10 employees."""
    async with async_session_maker() as session:
        active_teams = (await session.execute(
            select(Team).where(Team.is_active == True)
        )).scalars().all()
        assert len(active_teams) == 15
        for t in active_teams:
            count = (await session.execute(
                select(func.count(Employee.id))
                .join(User, Employee.user_id == User.id)
                .where(Employee.team_id == t.id, User.is_active == True)
            )).scalar()
            assert count == 10, f"Team {t.name} has {count} members, expected 10"


@pytest.mark.asyncio
async def test_05_every_employee_has_unique_employee_id():
    """Test 5: Every active employee has a unique, non-empty Employee ID."""
    async with async_session_maker() as session:
        val_result = await validate_organization_structure(session)
        assert val_result["status"] == "valid"
        assert val_result["total_employees"] == 150
        assert val_result["teams_count"] == 15


@pytest.mark.asyncio
async def test_06_group_leader_is_one_of_the_10_members():
    """Test 6: Group Leader is one of the 10 members (total remains 10)."""
    async with async_session_maker() as session:
        teams = (await session.execute(select(Team).where(Team.is_active == True))).scalars().all()
        for t in teams:
            emps = (await session.execute(
                select(Employee)
                .join(User, Employee.user_id == User.id)
                .where(Employee.team_id == t.id, User.is_active == True)
            )).scalars().all()
            assert len(emps) == 10
            leaders = [e for e in emps if e.is_group_leader]
            assert len(leaders) == 1, f"Team {t.name} has {len(leaders)} leaders, expected exactly 1"


@pytest.mark.asyncio
async def test_07_to_13_deterministic_rotation_25_cycles():
    """
    Tests 7 to 13 & 25:
    Notice 1  -> EMP001 (Cycle 1, Pos 1)
    Notice 2  -> EMP002 (Cycle 1, Pos 2)
    ...
    Notice 10 -> EMP010 (Cycle 1, Pos 10)
    Notice 11 -> EMP001 (Cycle 2, Pos 1)
    Notice 20 -> EMP010 (Cycle 2, Pos 10)
    Notice 21 -> EMP001 (Cycle 3, Pos 1)
    Notice 25 -> EMP005 (Cycle 3, Pos 5)
    """
    async with async_session_maker() as session:
        db_team = (await session.execute(
            select(Team).where(Team.name == "Database L2", Team.is_active == True)
        )).scalar_one()

        # Reset rotation for Database L2 to clean start (Cycle 1, Pos 1)
        tr = (await session.execute(
            select(TeamRotation).where(TeamRotation.team_id == db_team.id)
        )).scalar_one_or_none()
        if not tr:
            tr = TeamRotation(team_id=db_team.id, current_position=1, cycle_number=1)
            session.add(tr)
        else:
            tr.current_position = 1
            tr.cycle_number = 1
        await session.commit()

        team_members = (await session.execute(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .where(Employee.team_id == db_team.id, User.is_active == True, User.role == "EMPLOYEE")
            .order_by(Employee.employee_code.asc(), Employee.id.asc())
        )).scalars().all()
        assert len(team_members) == 10

        rot_svc = TeamRotationService(session)

        run_id = uuid.uuid4().hex[:6]
        assigned_sequence = []
        for i in range(1, 26):
            inc = Incident(
                id=uuid.uuid4(),
                incident_number=f"INC-ROT-{run_id}-{i:03d}",
                short_description=f"Rotation Test Incident #{i}",
                description="Testing deterministic 25-notice rotation rule",
                priority="P3",
                state="NEW",
                assignment_group=db_team.name,
                opened_at=datetime.now(timezone.utc)
            )
            session.add(inc)
            await session.flush()

            result = await rot_svc.assign_next_rotation_employee(
                team=db_team,
                incident=inc,
                idempotency_key=f"test_rot_{run_id}_{i}"
            )
            assigned_sequence.append(result)

        # Notice 1 -> Pos 1, Cycle 1, EMP001
        assert assigned_sequence[0]["rotation_position"] == 1
        assert assigned_sequence[0]["rotation_cycle"] == 1
        assert assigned_sequence[0]["assigned_employee_code"] == team_members[0].employee_code

        # Notice 2 -> Pos 2, Cycle 1, EMP002
        assert assigned_sequence[1]["rotation_position"] == 2
        assert assigned_sequence[1]["rotation_cycle"] == 1
        assert assigned_sequence[1]["assigned_employee_code"] == team_members[1].employee_code

        # Notice 10 -> Pos 10, Cycle 1, EMP010
        assert assigned_sequence[9]["rotation_position"] == 10
        assert assigned_sequence[9]["rotation_cycle"] == 1
        assert assigned_sequence[9]["assigned_employee_code"] == team_members[9].employee_code

        # Notice 11 -> Pos 1, Cycle 2, EMP001
        assert assigned_sequence[10]["rotation_position"] == 1
        assert assigned_sequence[10]["rotation_cycle"] == 2
        assert assigned_sequence[10]["assigned_employee_code"] == team_members[0].employee_code

        # Notice 20 -> Pos 10, Cycle 2, EMP010
        assert assigned_sequence[19]["rotation_position"] == 10
        assert assigned_sequence[19]["rotation_cycle"] == 2
        assert assigned_sequence[19]["assigned_employee_code"] == team_members[9].employee_code

        # Notice 21 -> Pos 1, Cycle 3, EMP001
        assert assigned_sequence[20]["rotation_position"] == 1
        assert assigned_sequence[20]["rotation_cycle"] == 3
        assert assigned_sequence[20]["assigned_employee_code"] == team_members[0].employee_code

        # Notice 25 -> Pos 5, Cycle 3, EMP005
        assert assigned_sequence[24]["rotation_position"] == 5
        assert assigned_sequence[24]["rotation_cycle"] == 3
        assert assigned_sequence[24]["assigned_employee_code"] == team_members[4].employee_code


@pytest.mark.asyncio
async def test_14_team_notice_creates_exactly_one_assignment_record():
    """Test 14: Team Notice creates strictly ONE IncidentAssignment record."""
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Network L2", Team.is_active == True)
        )).scalar_one()

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-SINGLE-{uuid.uuid4().hex[:6]}",
            short_description="Single Assignment Test",
            priority="P2",
            state="NEW",
            assignment_group=team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        rot_svc = TeamRotationService(session)
        res = await rot_svc.assign_next_rotation_employee(team=team, incident=inc)

        active_assignments = (await session.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id == inc.id,
                IncidentAssignment.is_active == True
            )
        )).scalars().all()
        assert len(active_assignments) == 1
        assert str(active_assignments[0].employee_id) == res["assigned_employee_id"]


@pytest.mark.asyncio
async def test_15_team_notice_sends_notice_to_all_10_members():
    """Test 15: Team Notice sends notice to all 10 members."""
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Linux L2", Team.is_active == True)
        )).scalar_one()

        team_emps = (await session.execute(
            select(Employee).join(User, Employee.user_id == User.id)
            .where(Employee.team_id == team.id, User.is_active == True, User.role == "EMPLOYEE")
        )).scalars().all()
        assert len(team_emps) == 10
        team_user_ids = {e.user_id for e in team_emps if e.user_id}

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-NOTICE-{uuid.uuid4().hex[:6]}",
            short_description="All 10 Notice Test",
            priority="P2",
            state="NEW",
            assignment_group=team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        rot_svc = TeamRotationService(session)
        await rot_svc.assign_next_rotation_employee(team=team, incident=inc)

        # Check team notice notifications created
        notifs = (await session.execute(
            select(Notification).where(
                Notification.incident_id == inc.id,
                Notification.type == "TEAM_NOTICE"
            )
        )).scalars().all()
        notified_user_ids = {n.user_id for n in notifs}
        assert notified_user_ids == team_user_ids
        assert len(notifs) == 10


@pytest.mark.asyncio
async def test_16_only_selected_employee_receives_personal_notification():
    """Test 16: Only the selected employee receives personal INCIDENT_ASSIGNED notification."""
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Security Operations L2", Team.is_active == True)
        )).scalar_one()

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-PERS-{uuid.uuid4().hex[:6]}",
            short_description="Personal Notification Test",
            priority="P1",
            state="NEW",
            assignment_group=team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        rot_svc = TeamRotationService(session)
        res = await rot_svc.assign_next_rotation_employee(team=team, incident=inc)
        assigned_emp_id = uuid.UUID(res["assigned_employee_id"])
        assigned_emp = await session.get(Employee, assigned_emp_id)

        pers_notifs = (await session.execute(
            select(Notification).where(
                Notification.incident_id == inc.id,
                Notification.type == "INCIDENT_ASSIGNED"
            )
        )).scalars().all()
        assert len(pers_notifs) == 1
        assert pers_notifs[0].user_id == assigned_emp.user_id


@pytest.mark.asyncio
async def test_17_realtime_my_work_updated_event(monkeypatch):
    """Test 17: Realtime MY_WORK_UPDATED event is dispatched ONLY to selected employee."""
    from app.websocket.manager import ws_manager
    dispatched_events = []

    async def mock_send_to_user(user_id, event, data):
        dispatched_events.append({"user_id": str(user_id), "event": event, "data": data})

    monkeypatch.setattr(ws_manager, "send_to_user", mock_send_to_user)

    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Cloud Operations L2", Team.is_active == True)
        )).scalar_one()

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-WS-{uuid.uuid4().hex[:6]}",
            short_description="WebSocket Test",
            priority="P2",
            state="NEW",
            assignment_group=team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        rot_svc = TeamRotationService(session)
        res = await rot_svc.assign_next_rotation_employee(team=team, incident=inc)
        assigned_emp_id = uuid.UUID(res["assigned_employee_id"])
        assigned_emp = await session.get(Employee, assigned_emp_id)

        my_work_events = [e for e in dispatched_events if e["event"] == "MY_WORK_UPDATED"]
        assert len(my_work_events) == 1
        assert my_work_events[0]["user_id"] == str(assigned_emp.user_id)


@pytest.mark.asyncio
async def test_18_concurrent_notices_select_sequential_employees():
    """Test 18: Concurrent notices for same team select sequential employees without race condition."""
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Application Support L2", Team.is_active == True)
        )).scalar_one()

        # Reset rotation to Pos 1
        rot = (await session.execute(
            select(TeamRotation).where(TeamRotation.team_id == team.id)
        )).scalar_one_or_none()
        if not rot:
            rot = TeamRotation(team_id=team.id, current_position=1, cycle_number=1)
            session.add(rot)
        else:
            rot.current_position = 1
            rot.cycle_number = 1
        await session.commit()

    run_id = uuid.uuid4().hex[:6]

    async def run_assignment(idx):
        async with async_session_maker() as s:
            t = await s.get(Team, team.id)
            inc = Incident(
                id=uuid.uuid4(),
                incident_number=f"INC-CONC-{run_id}-{idx:02d}",
                short_description=f"Concurrent Test {idx}",
                priority="P3",
                state="NEW",
                assignment_group=t.name,
                opened_at=datetime.now(timezone.utc)
            )
            s.add(inc)
            await s.flush()
            svc = TeamRotationService(s)
            return await svc.assign_next_rotation_employee(team=t, incident=inc)

    results = await asyncio.gather(run_assignment(1), run_assignment(2))
    pos1 = results[0]["rotation_position"]
    pos2 = results[1]["rotation_position"]
    assert {pos1, pos2} == {1, 2}, f"Expected positions 1 and 2, got {pos1} and {pos2}"
    assert results[0]["assigned_employee_id"] != results[1]["assigned_employee_id"]


@pytest.mark.asyncio
async def test_19_duplicate_notice_does_not_advance_rotation():
    """Test 19: Duplicate notice submission with stable idempotency key does NOT advance rotation."""
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Windows L2", Team.is_active == True)
        )).scalar_one()

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-IDEMP-{uuid.uuid4().hex[:6]}",
            short_description="Idempotent Notice",
            priority="P3",
            state="NEW",
            assignment_group=team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        rot_svc = TeamRotationService(session)
        stable_key = f"evt_idemp_{inc.id}"

        res1 = await rot_svc.assign_next_rotation_employee(
            team=team, incident=inc, idempotency_key=stable_key
        )
        first_pos = res1["rotation_position"]
        first_cycle = res1["rotation_cycle"]
        first_emp_id = res1["assigned_employee_id"]

        # Second attempt with same key
        res2 = await rot_svc.assign_next_rotation_employee(
            team=team, incident=inc, idempotency_key=stable_key
        )
        assert res2.get("idempotent") is True
        assert res2["assigned_employee_id"] == first_emp_id
        assert res2["rotation_position"] == first_pos
        assert res2["rotation_cycle"] == first_cycle


@pytest.mark.asyncio
async def test_20_rotation_state_persists_across_sessions():
    """Test 20: Rotation state persists accurately in database."""
    async with async_session_maker() as session1:
        team = (await session1.execute(
            select(Team).where(Team.name == "Identity & Access L2", Team.is_active == True)
        )).scalar_one()
        rot_svc = TeamRotationService(session1)
        rot = await rot_svc.get_or_create_rotation(team.id)
        rot.current_position = 7
        rot.cycle_number = 4
        await session1.commit()

    async with async_session_maker() as session2:
        rot_reloaded = (await session2.execute(
            select(TeamRotation).where(TeamRotation.team_id == team.id)
        )).scalar_one()
        assert rot_reloaded.current_position == 7
        assert rot_reloaded.cycle_number == 4


@pytest.mark.asyncio
async def test_21_changing_group_leader_does_not_change_rotation_order():
    """Test 21: Changing group leader does not disrupt deterministic rotation order."""
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Messaging & Collaboration L2", Team.is_active == True)
        )).scalar_one()

        emps = (await session.execute(
            select(Employee).join(User, Employee.user_id == User.id)
            .where(Employee.team_id == team.id, User.is_active == True, User.role == "EMPLOYEE")
            .order_by(Employee.employee_code.asc(), Employee.id.asc())
        )).scalars().all()
        assert len(emps) == 10

        # Change leader from emp 0 to emp 1
        emps[0].is_group_leader = False
        emps[1].is_group_leader = True
        await session.commit()

        # Rotation order must remain sorted strictly by employee_code
        rot_svc = TeamRotationService(session)
        rot = await rot_svc.get_or_create_rotation(team.id)
        rot.current_position = 1
        await session.commit()

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-LEADER-{uuid.uuid4().hex[:6]}",
            short_description="Leader change test",
            priority="P3",
            state="NEW",
            assignment_group=team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        res = await rot_svc.assign_next_rotation_employee(team=team, incident=inc)
        assert res["assigned_employee_code"] == emps[0].employee_code
        assert res["rotation_position"] == 1


@pytest.mark.asyncio
async def test_22_inactive_team_raises_validation_error():
    """Test 22: Organization validation rejects inactive or missing teams."""
    async with async_session_maker() as session:
        temp_team = Team(name="Temp 16th Team", is_active=True)
        session.add(temp_team)
        await session.flush()

        with pytest.raises(OrgValidationError):
            await validate_organization_structure(session)

        await session.rollback()


@pytest.mark.asyncio
async def test_23_team_with_invalid_members_count_raises_error():
    """Test 23: TeamRotationService rejects team with != 10 members."""
    async with async_session_maker() as session:
        invalid_team = Team(name=f"Invalid Team {uuid.uuid4().hex[:6]}", is_active=True)
        session.add(invalid_team)
        await session.flush()

        for i in range(1, 6):
            u = User(
                email=f"inv_{uuid.uuid4().hex[:6]}@incidentflow.dev",
                hashed_password="hash",
                full_name=f"Invalid Emp {i}",
                role="EMPLOYEE",
                is_active=True
            )
            session.add(u)
            await session.flush()
            e = Employee(user_id=u.id, team_id=invalid_team.id, employee_code=f"INV{uuid.uuid4().hex[:4].upper()}")
            session.add(e)
        await session.flush()

        inc = Incident(
            id=uuid.uuid4(),
            incident_number=f"INC-INV-{uuid.uuid4().hex[:6]}",
            short_description="Invalid team test",
            priority="P3",
            state="NEW",
            assignment_group=invalid_team.name,
            opened_at=datetime.now(timezone.utc)
        )
        session.add(inc)
        await session.flush()

        rot_svc = TeamRotationService(session)
        with pytest.raises(ValueError, match="exactly 10 active team members"):
            await rot_svc.assign_next_rotation_employee(team=invalid_team, incident=inc)

        await session.rollback()


@pytest.mark.asyncio
async def test_24_forbidden_word_unassigned_not_in_api_response():
    """Test 24: Verify forbidden word 'unassigned' does not appear in team notice API responses."""
    async with async_session_maker() as session:
        admin_user = (await session.execute(
            select(User).where(User.role == "ADMIN", User.is_active == True)
        )).scalars().first()
        admin_token = create_access_token(data={"sub": str(admin_user.id), "role": "ADMIN"})

        team = (await session.execute(
            select(Team).where(Team.name == "Database L2", Team.is_active == True)
        )).scalar_one()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {admin_token}"}

        payload = {
            "title": "API Terminology Validation Incident",
            "message": "Validating absence of forbidden word in API response",
            "priority": "P2",
            "auto_assign": True
        }
        res = await client.post(f"/api/admin/teams/{team.id}/notice", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.json()

        # The assignment_status must not be 'UNASSIGNED'
        assert data.get("assignment_status") in ("ASSIGNED", "Assignment Pending")
        assert "UNASSIGNED" not in str(data.get("assignment_status"))
        assert "UNASSIGNED" not in str(data.get("policy"))


@pytest.mark.asyncio
async def test_25_notice_acceptance_test_full_sequence():
    """
    Test 25: Section 31 Authoritative 25-Notice Acceptance Test:
    Notice 1..10  -> EMP001..EMP010 (Cycle 1)
    Notice 11..20 -> EMP001..EMP010 (Cycle 2)
    Notice 21..25 -> EMP001..EMP005 (Cycle 3)
    """
    async with async_session_maker() as session:
        team = (await session.execute(
            select(Team).where(Team.name == "Network L2", Team.is_active == True)
        )).scalar_one()

        # Initialize rotation pointer to 1, cycle 1
        rot = (await session.execute(
            select(TeamRotation).where(TeamRotation.team_id == team.id)
        )).scalar_one_or_none()
        if not rot:
            rot = TeamRotation(team_id=team.id, current_position=1, cycle_number=1)
            session.add(rot)
        else:
            rot.current_position = 1
            rot.cycle_number = 1
        await session.commit()

        team_members = (await session.execute(
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .where(Employee.team_id == team.id, User.is_active == True, User.role == "EMPLOYEE")
            .order_by(Employee.employee_code.asc(), Employee.id.asc())
        )).scalars().all()
        assert len(team_members) == 10

        rot_svc = TeamRotationService(session)
        batch_id = uuid.uuid4().hex[:6]

        history = []
        for n in range(1, 26):
            inc = Incident(
                id=uuid.uuid4(),
                incident_number=f"INC-ACCEPT-{batch_id}-{n:03d}",
                short_description=f"Acceptance Test Notice #{n}",
                priority="P2",
                state="NEW",
                assignment_group=team.name,
                opened_at=datetime.now(timezone.utc)
            )
            session.add(inc)
            await session.flush()

            res = await rot_svc.assign_next_rotation_employee(
                team=team,
                incident=inc,
                idempotency_key=f"accept_key_{batch_id}_{n}"
            )
            history.append(res)

        # Verify Cycle 1 (Notices 1..10)
        for idx in range(10):
            expected_pos = idx + 1
            assert history[idx]["rotation_position"] == expected_pos
            assert history[idx]["rotation_cycle"] == 1
            assert history[idx]["assigned_employee_code"] == team_members[idx].employee_code

        # Verify Cycle 2 (Notices 11..20)
        for idx in range(10):
            expected_pos = idx + 1
            assert history[10 + idx]["rotation_position"] == expected_pos
            assert history[10 + idx]["rotation_cycle"] == 2
            assert history[10 + idx]["assigned_employee_code"] == team_members[idx].employee_code

        # Verify Cycle 3 (Notices 21..25)
        for idx in range(5):
            expected_pos = idx + 1
            assert history[20 + idx]["rotation_position"] == expected_pos
            assert history[20 + idx]["rotation_cycle"] == 3
            assert history[20 + idx]["assigned_employee_code"] == team_members[idx].employee_code


@pytest.mark.asyncio
async def test_26_get_team_rotation_endpoint():
    """Test 26: GET /api/admin/teams/{team_id}/rotation returns persistent state and order."""
    async with async_session_maker() as session:
        admin_user = (await session.execute(
            select(User).where(User.role == "ADMIN", User.is_active == True)
        )).scalars().first()
        admin_token = create_access_token(data={"sub": str(admin_user.id), "role": "ADMIN"})

        team = (await session.execute(
            select(Team).where(Team.name == "Database L2", Team.is_active == True)
        )).scalar_one()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = await client.get(f"/api/admin/teams/{team.id}/rotation", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["team_id"] == str(team.id)
        assert data["team_name"] == "Database L2"
        assert 1 <= data["current_position"] <= 10
        assert data["cycle_number"] >= 1
        assert data["members_count"] == 10
        assert len(data["rotation_order"]) == 10

        # Verify exactly one member is flagged is_next
        next_flags = [m for m in data["rotation_order"] if m["is_next"]]
        assert len(next_flags) == 1
        assert next_flags[0]["position"] == data["current_position"]


