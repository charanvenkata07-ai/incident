import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.conversation import Conversation, ConversationMember, ChatMessage
from app.models.task_template import TaskTemplate
from app.models.notification import Notification


@pytest.mark.asyncio
async def test_admin_global_search_all_scopes():
    """
    Verify that an ADMIN user can search across all authorized categories:
    employees, teams, incidents, tasks, work, chat, notifications.
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        assert admin_user is not None

        # Seed an incident with unique text
        unique_token = uuid.uuid4().hex[:8].upper()
        inc = Incident(
            incident_number=f"INC-SRCH-{unique_token}",
            short_description=f"Global Search Unique Query {unique_token}",
            priority="P1",
            state="NEW",
            assignment_group="Database L2"
        )
        session.add(inc)

        # Seed a unique task
        task = TaskTemplate(
            team_id=(await session.execute(select(Team.id))).scalars().first(),
            title=f"Task Search Target {unique_token}",
            description=f"Specific recovery checklist {unique_token}"
        )
        session.add(task)
        await session.commit()

    admin_token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})
    headers = {"Authorization": f"Bearer {admin_token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Search for the unique token
        res = await ac.get(f"/api/search?q={unique_token}", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["total_count"] >= 2
        categories = data["categories"]

        # Incident match
        inc_matches = [i for i in categories["incidents"] if unique_token in i["incident_number"] or unique_token in i["short_description"]]
        assert len(inc_matches) >= 1
        assert inc_matches[0]["incident_number"] == f"INC-SRCH-{unique_token}"

        # Task match
        task_matches = [t for t in categories["tasks"] if unique_token in t["title"]]
        assert len(task_matches) >= 1
        assert task_matches[0]["title"] == f"Task Search Target {unique_token}"


@pytest.mark.asyncio
async def test_employee_data_isolation_between_teams():
    """
    Verify strict cross-team isolation:
    Employee in Team A can search Team A employees, incidents, and tasks.
    Employee in Team A CANNOT discover Team B employees, incidents, or tasks.
    """
    async with async_session_maker() as session:
        # Create Team A and Team B
        tag = uuid.uuid4().hex[:6]
        team_a = Team(name=f"Search Team Alpha {tag}")
        team_b = Team(name=f"Search Team Beta {tag}")
        session.add_all([team_a, team_b])
        await session.flush()

        # Employee A in Team A
        user_a = User(email=f"alpha_{tag}@example.com", full_name=f"Alpha Member {tag}", role="EMPLOYEE", hashed_password="mock_password")
        session.add(user_a)
        await session.flush()
        emp_a = Employee(user_id=user_a.id, team_id=team_a.id, employee_code=f"EMP-A-{tag}", availability_status="AVAILABLE")
        session.add(emp_a)

        # Teammate A2 in Team A
        user_a2 = User(email=f"alpha2_{tag}@example.com", full_name=f"Alpha SecretTeammate {tag}", role="EMPLOYEE", hashed_password="mock_password")
        session.add(user_a2)
        await session.flush()
        emp_a2 = Employee(user_id=user_a2.id, team_id=team_a.id, employee_code=f"EMP-A2-{tag}", availability_status="AVAILABLE")
        session.add(emp_a2)

        # Employee B in Team B
        user_b = User(email=f"beta_{tag}@example.com", full_name=f"Beta RestrictedUser {tag}", role="EMPLOYEE", hashed_password="mock_password")
        session.add(user_b)
        await session.flush()
        emp_b = Employee(user_id=user_b.id, team_id=team_b.id, employee_code=f"EMP-B-{tag}", availability_status="AVAILABLE")
        session.add(emp_b)

        # Incident A for Team A
        inc_a = Incident(
            incident_number=f"INC-A-{tag}",
            short_description=f"Alpha Incident Only {tag}",
            assignment_group=team_a.name
        )
        # Incident B for Team B
        inc_b = Incident(
            incident_number=f"INC-B-{tag}",
            short_description=f"Beta Restricted Incident {tag}",
            assignment_group=team_b.name
        )
        session.add_all([inc_a, inc_b])

        # Task for Team B
        task_b = TaskTemplate(
            team_id=team_b.id,
            title=f"Beta Confidential Task {tag}",
            description="Restricted procedure"
        )
        session.add(task_b)
        await session.commit()

        user_a_id = user_a.id

    token_a = create_access_token(data={"sub": str(user_a_id), "role": "EMPLOYEE"})
    headers_a = {"Authorization": f"Bearer {token_a}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Search for teammate in Team A -> MUST SUCCEED
        res_team_a = await ac.get(f"/api/search?q=SecretTeammate {tag}", headers=headers_a)
        assert res_team_a.status_code == 200
        emp_res = res_team_a.json()["categories"]["employees"]
        assert len(emp_res) == 1
        assert emp_res[0]["full_name"] == f"Alpha SecretTeammate {tag}"

        # 2. Attempt to search for Team B employee -> MUST RETURN ZERO RESULTS (No leak)
        res_team_b = await ac.get(f"/api/search?q=RestrictedUser {tag}", headers=headers_a)
        assert res_team_b.status_code == 200
        assert len(res_team_b.json()["categories"]["employees"]) == 0

        # 3. Attempt to search for Team B incident -> MUST RETURN ZERO RESULTS
        res_inc_b = await ac.get(f"/api/search?q=INC-B-{tag}", headers=headers_a)
        assert res_inc_b.status_code == 200
        assert len(res_inc_b.json()["categories"]["incidents"]) == 0

        # 4. Search for Team A incident -> MUST SUCCEED
        res_inc_a = await ac.get(f"/api/search?q=INC-A-{tag}", headers=headers_a)
        assert res_inc_a.status_code == 200
        assert len(res_inc_a.json()["categories"]["incidents"]) == 1
        assert res_inc_a.json()["categories"]["incidents"][0]["incident_number"] == f"INC-A-{tag}"

        # 5. Attempt to search for Team B task template -> MUST RETURN ZERO RESULTS
        res_task_b = await ac.get(f"/api/search?q=Confidential Task {tag}", headers=headers_a)
        assert res_task_b.status_code == 200
        assert len(res_task_b.json()["categories"]["tasks"]) == 0


@pytest.mark.asyncio
async def test_chat_search_authorization_and_leader_revocation():
    """
    Verify chat search security:
    - Group Leader can search messages in their ADMIN_TEAM chat.
    - Normal employee in the same team CANNOT search or discover ADMIN_TEAM chat.
    - When Group Leader role is transferred to another member, former leader CANNOT search ADMIN_TEAM chat.
    """
    tag = uuid.uuid4().hex[:6]
    secret_msg_content = f"Confidential Admin Leader Communication {tag}"

    async with async_session_maker() as session:
        team = Team(name=f"Chat Sec Team {tag}")
        session.add(team)
        await session.flush()

        # Leader 1 (Alice)
        user_leader1 = User(email=f"leader1_{tag}@example.com", full_name=f"Leader Alice {tag}", role="EMPLOYEE", hashed_password="mock_password")
        session.add(user_leader1)
        await session.flush()
        emp_leader1 = Employee(user_id=user_leader1.id, team_id=team.id, is_group_leader=True)
        session.add(emp_leader1)

        # Non-leader (Bob)
        user_bob = User(email=f"bob_{tag}@example.com", full_name=f"Bob Teammate {tag}", role="EMPLOYEE", hashed_password="mock_password")
        session.add(user_bob)
        await session.flush()
        emp_bob = Employee(user_id=user_bob.id, team_id=team.id, is_group_leader=False)
        session.add(emp_bob)

        # ADMIN_TEAM conversation
        admin_conv = Conversation(type="ADMIN_TEAM", team_id=team.id, title=f"Admin Team {team.name}")
        session.add(admin_conv)
        await session.flush()

        # Add message in ADMIN_TEAM
        msg = ChatMessage(
            conversation_id=admin_conv.id,
            sender_id=user_leader1.id,
            content=secret_msg_content,
            message_type="TEXT"
        )
        session.add(msg)
        await session.commit()

        u_leader1_id = user_leader1.id
        u_bob_id = user_bob.id
        emp_leader1_id = emp_leader1.id
        team_id = team.id

    transport = ASGITransport(app=app)

    # 1. Leader Alice searches for secret message -> MUST SUCCEED
    token_alice = create_access_token(data={"sub": str(u_leader1_id), "role": "EMPLOYEE"})
    headers_alice = {"Authorization": f"Bearer {token_alice}"}

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_alice = await ac.get(f"/api/search?q={secret_msg_content}&scope=chat", headers=headers_alice)
        assert res_alice.status_code == 200
        matches = res_alice.json()["categories"]["chat"]
        assert len(matches) == 1
        assert secret_msg_content in matches[0]["content"]

        # 2. Non-leader Bob searches for secret message -> MUST BE ZERO (Blocked)
        token_bob = create_access_token(data={"sub": str(u_bob_id), "role": "EMPLOYEE"})
        headers_bob = {"Authorization": f"Bearer {token_bob}"}
        res_bob = await ac.get(f"/api/search?q={secret_msg_content}&scope=chat", headers=headers_bob)
        assert res_bob.status_code == 200
        assert len(res_bob.json()["categories"]["chat"]) == 0

    # 3. Transfer leadership: Demote Alice, promote Bob
    async with async_session_maker() as session:
        emp_a = await session.get(Employee, emp_leader1_id)
        emp_a.is_group_leader = False
        emp_b_db = (await session.execute(select(Employee).where(Employee.user_id == u_bob_id))).scalar_one()
        emp_b_db.is_group_leader = True
        await session.commit()

    # 4. Now Alice (former leader) searches again -> MUST BE STRICTLY BLOCKED ON DATABASE CHECK
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_former = await ac.get(f"/api/search?q={secret_msg_content}&scope=chat", headers=headers_alice)
        assert res_former.status_code == 200
        assert len(res_former.json()["categories"]["chat"]) == 0

        # Bob (new leader) searches -> MUST SUCCEED
        res_new_leader = await ac.get(f"/api/search?q={secret_msg_content}&scope=chat", headers=headers_bob)
        assert res_new_leader.status_code == 200
        assert len(res_new_leader.json()["categories"]["chat"]) == 1


@pytest.mark.asyncio
async def test_search_sanitization_and_normalization():
    """
    Verify:
    1. Search output contains NO password hashes, tokens, or private secrets.
    2. Case-insensitivity (e.g. 'dAtAbAsE' matches 'Database').
    3. Whitespace normalization.
    4. Empty search returns clean 0 count without error.
    """
    async with async_session_maker() as session:
        admin_user = (await session.execute(select(User).where(User.role == "ADMIN"))).scalars().first()
        token = create_access_token(data={"sub": str(admin_user.id), "role": admin_user.role})

    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Case insensitive test
        res_mixed = await ac.get("/api/search?q=dAtAbAsE", headers=headers)
        assert res_mixed.status_code == 200
        data = res_mixed.json()
        assert data["total_count"] > 0

        # Ensure no sensitive keys in any returned object
        for category, items in data["categories"].items():
            for item in items:
                assert "hashed_password" not in item
                assert "password" not in item
                assert "token" not in item
                assert "secret" not in item
                assert "api_key" not in item

        # Whitespace normalization
        res_ws = await ac.get("/api/search?q=   database   ", headers=headers)
        assert res_ws.status_code == 200
        assert res_ws.json()["query"] == "database"
        assert res_ws.json()["total_count"] == data["total_count"]

        # Empty search
        res_empty = await ac.get("/api/search?q=", headers=headers)
        assert res_empty.status_code == 200
        assert res_empty.json()["total_count"] == 0
