import pytest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.audit import AuditLog
from app.models.settings import SystemSetting
from app.services.audit_service import AuditService

@pytest.mark.asyncio
async def test_audit_service_accepts_request_id_and_kwargs():
    async with async_session_maker() as session:
        audit = AuditService(session)
        # Must not raise TypeError
        await audit.log(
            action='AUTOMATION_STATUS_CHANGED',
            entity_type='SYSTEM',
            old_value={'status': 'ACTIVE'},
            new_value={'status': 'PAUSED'},
            reason='Emergency Pause Test',
            request_id='req-test-12345',
            ip_address='127.0.0.1',
            custom_extra_param='test'
        )
        await session.commit()

        # Verify record in DB
        res = await session.execute(
            select(AuditLog).where(AuditLog.action == 'AUTOMATION_STATUS_CHANGED').order_by(AuditLog.created_at.desc()).limit(1)
        )
        record = res.scalar_one()
        assert record.request_id == 'req-test-12345'
        assert record.ip_address == '127.0.0.1'

@pytest.mark.asyncio
async def test_pause_and_resume_automation_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        async with async_session_maker() as session:
            admin_res = await session.execute(select(User).where(User.role == 'ADMIN', User.is_active == True).limit(1))
            admin_user = admin_res.scalar_one()
        admin_token = create_access_token({'sub': str(admin_user.id), 'role': admin_user.role})
        admin_headers = {'Authorization': f'Bearer {admin_token}'}

        # 1. Pause Automation
        pause_res = await client.post('/api/admin/automation/pause', headers=admin_headers)
        assert pause_res.status_code == 200, pause_res.text
        pause_data = pause_res.json()
        assert pause_data['status'] == 'paused'
        assert pause_data['automation_mode'] == 'PAUSED'
        assert pause_data['auto_assignment_enabled'] is False

        # Verify Dashboard stats reflects PAUSED
        dash_res1 = await client.get('/api/admin/dashboard', headers=admin_headers)
        assert dash_res1.status_code == 200
        dash_data1 = dash_res1.json()
        assert dash_data1['automation_mode'] == 'PAUSED'
        assert dash_data1['auto_assignment_enabled'] is False

        # 2. Resume Automation
        resume_res = await client.post('/api/admin/automation/resume', headers=admin_headers)
        assert resume_res.status_code == 200, resume_res.text
        resume_data = resume_res.json()
        assert resume_data['status'] == 'active'
        assert resume_data['auto_assignment_enabled'] is True
        assert resume_data['automation_mode'] != 'PAUSED'

        # Verify Dashboard stats reflects resumed
        dash_res2 = await client.get('/api/admin/dashboard', headers=admin_headers)
        assert dash_res2.status_code == 200
        dash_data2 = dash_res2.json()
        assert dash_data2['auto_assignment_enabled'] is True
        assert dash_data2['automation_mode'] != 'PAUSED'

@pytest.mark.asyncio
async def test_live_assignments_board_full_history():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        async with async_session_maker() as session:
            team_res = await session.execute(select(Team).limit(1))
            team = team_res.scalar_one()

            emp_res = await session.execute(
                select(Employee, User).join(User, Employee.user_id == User.id).where(
                    Employee.team_id == team.id,
                    User.is_active == True
                ).limit(2)
            )
            emps = emp_res.all()
            emp1, user1 = emps[0]
            emp2, user2 = emps[1]

            admin_res = await session.execute(select(User).where(User.role == 'ADMIN', User.is_active == True).limit(1))
            admin_user = admin_res.scalar_one()

            # Create Incident 1 (Completed by Emp 1)
            inc1 = Incident(
                id=uuid.uuid4(),
                incident_number=f'INC-HIST-1-{uuid.uuid4().hex[:6].upper()}',
                short_description='Historical Completed Task',
                priority='P1',
                state='RESOLVED',
                assignment_group=team.name
            )
            session.add(inc1)
            await session.flush()

            assign1 = IncidentAssignment(
                id=uuid.uuid4(),
                incident_id=inc1.id,
                employee_id=emp1.id,
                status='COMPLETED',
                assignment_type='AUTOMATIC',
                is_active=False,
                assigned_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            session.add(assign1)

            # Create Incident 2 (In Progress by Emp 2)
            inc2 = Incident(
                id=uuid.uuid4(),
                incident_number=f'INC-HIST-2-{uuid.uuid4().hex[:6].upper()}',
                short_description='Active In-Progress Task',
                priority='P2',
                state='IN_PROGRESS',
                assignment_group=team.name
            )
            session.add(inc2)
            await session.flush()

            assign2 = IncidentAssignment(
                id=uuid.uuid4(),
                incident_id=inc2.id,
                employee_id=emp2.id,
                status='IN_PROGRESS',
                assignment_type='AUTOMATIC',
                is_active=True,
                assigned_at=datetime.now(timezone.utc),
                started_at=datetime.now(timezone.utc)
            )
            session.add(assign2)
            await session.commit()

        admin_token = create_access_token({'sub': str(admin_user.id), 'role': admin_user.role})
        admin_headers = {'Authorization': f'Bearer {admin_token}'}

        res = await client.get('/api/admin/assignments/live', headers=admin_headers)
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)

        # Verify both items are present in history without deduplication
        found1 = next((x for x in items if x['incident_number'] == inc1.incident_number), None)
        found2 = next((x for x in items if x['incident_number'] == inc2.incident_number), None)

        assert found1 is not None, 'Completed historical incident must be present in Live Board'
        assert found1['status'] == 'COMPLETED'
        assert found1['employee_name'] == user1.full_name
        assert found1['completed_at'] is not None

        assert found2 is not None, 'In-progress incident must be present in Live Board'
        assert found2['status'] == 'IN_PROGRESS'
        assert found2['employee_name'] == user2.full_name

@pytest.mark.asyncio
async def test_automation_mode_switching_dry_run_shadow_live():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        async with async_session_maker() as session:
            admin_res = await session.execute(select(User).where(User.role == 'ADMIN', User.is_active == True).limit(1))
            admin_user = admin_res.scalar_one()

        admin_token = create_access_token({'sub': str(admin_user.id), 'role': admin_user.role})
        admin_headers = {'Authorization': f'Bearer {admin_token}'}

        # 1. Switch to DRY_RUN
        res_dry = await client.post('/api/admin/automation/mode', headers=admin_headers, json={'mode': 'DRY_RUN', 'confirmed': True})
        assert res_dry.status_code == 200, res_dry.text
        data_dry = res_dry.json()
        assert data_dry['mode'] == 'DRY_RUN'
        assert data_dry['dry_run_mode'] is True
        assert data_dry['shadow_mode'] is False

        # 2. Switch to SHADOW
        res_shadow = await client.post('/api/admin/automation/mode', headers=admin_headers, json={'mode': 'SHADOW', 'confirmed': True})
        assert res_shadow.status_code == 200, res_shadow.text
        data_shadow = res_shadow.json()
        assert data_shadow['mode'] == 'SHADOW'
        assert data_shadow['dry_run_mode'] is False
        assert data_shadow['shadow_mode'] is True

        # 3. Switch to LIVE requires exact phrase
        fail_live = await client.post('/api/admin/automation/mode', headers=admin_headers, json={'mode': 'LIVE', 'confirmed': True, 'confirmation_phrase': 'WRONG'})
        assert fail_live.status_code == 400

        # Switch to LIVE with exact phrase
        ok_live = await client.post('/api/admin/automation/mode', headers=admin_headers, json={'mode': 'LIVE', 'confirmed': True, 'confirmation_phrase': 'ENABLE LIVE ASSIGNMENT'})
        assert ok_live.status_code == 200, ok_live.text
        data_live = ok_live.json()
        assert data_live['mode'] == 'LIVE'
        assert data_live['dry_run_mode'] is False
        assert data_live['shadow_mode'] is False
        assert data_live['auto_assignment_enabled'] is True
