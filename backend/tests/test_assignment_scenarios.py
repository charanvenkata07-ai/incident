import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.models.employee import Employee
from app.models.incident import Incident
from app.models.user import User
from app.services.assignment_engine import AssignmentEngine

def create_mock_employee(name: str, workload: int = 0, skills: list = None):
    emp_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), full_name=name, email=f"{name.lower()}@test.com", role="EMPLOYEE")
    emp = Employee(
        id=emp_id,
        user_id=user.id,
        availability_status="AVAILABLE",
        is_present=True,
    )
    emp.user = user
    emp.skills = skills or []
    return emp

@pytest.mark.asyncio
async def test_least_workload_strategy():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    
    emp_ravi = create_mock_employee("Ravi")
    emp_kiran = create_mock_employee("Kiran")
    eligible = [emp_ravi, emp_kiran]
    
    # Mock workload service
    engine.workload_service.get_workloads = AsyncMock(return_value={
        emp_ravi.id: 3,
        emp_kiran.id: 1
    })
    
    selected = await engine._least_workload(eligible)
    assert selected.id == emp_kiran.id
    assert selected.user.full_name == "Kiran"

@pytest.mark.asyncio
async def test_round_robin_strategy():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    
    emp1 = create_mock_employee("Emp1")
    emp2 = create_mock_employee("Emp2")
    eligible = sorted([emp1, emp2], key=lambda e: str(e.id))
    
    # When last assigned is eligible[0], next should be eligible[1]
    engine._get_last_assigned_employee = AsyncMock(return_value=eligible[0].id)
    selected = await engine._round_robin(eligible)
    assert selected.id == eligible[1].id
    
    # When last assigned is eligible[1], next should wrap around to eligible[0]
    engine._get_last_assigned_employee = AsyncMock(return_value=eligible[1].id)
    selected_wrap = await engine._round_robin(eligible)
    assert selected_wrap.id == eligible[0].id

@pytest.mark.asyncio
async def test_zero_eligible_employees():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    
    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969716",
        short_description="Network degradation",
        priority="P3"
    )
    
    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[])
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_required_skills = AsyncMock(return_value=set())
    engine._handle_no_eligible = AsyncMock()
    
    assignment = await engine.process_incident(incident)
    assert assignment is None
    engine._handle_no_eligible.assert_called_once_with(incident)

@pytest.mark.asyncio
async def test_one_available_employee():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)
    
    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969714",
        short_description="MDM Sync issue",
        priority="P3"
    )
    
    emp_ravi = create_mock_employee("Ravi")
    engine.workload_service.get_workloads = AsyncMock(return_value={emp_ravi.id: 1})
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_required_skills = AsyncMock(return_value=set())
    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_ravi])
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")
    engine._is_dry_run = AsyncMock(return_value=False)
    engine._is_shadow_mode = AsyncMock(return_value=False)
    
    mock_assignment = MagicMock()
    engine._create_assignment = AsyncMock(return_value=mock_assignment)
    
    assignment = await engine.process_incident(incident)
    assert assignment == mock_assignment
    engine._create_assignment.assert_called_once_with(incident, emp_ravi, "LEAST_WORKLOAD")

@pytest.mark.asyncio
async def test_shadow_mode_decision_logging():
    mock_db = AsyncMock()
    engine = AssignmentEngine(mock_db)

    incident = Incident(
        id=uuid.uuid4(),
        incident_number="INC1969799",
        short_description="Shadow verification test incident",
        priority="P2"
    )

    emp_ravi = create_mock_employee("Ravi")
    engine._is_auto_assignment_enabled = AsyncMock(return_value=True)
    engine._get_required_skills = AsyncMock(return_value=set())
    engine.eligibility.find_eligible_employees = AsyncMock(return_value=[emp_ravi])
    engine._get_strategy = AsyncMock(return_value="LEAST_WORKLOAD")
    engine.workload_service.get_workloads = AsyncMock(return_value={emp_ravi.id: 0})
    engine._is_dry_run = AsyncMock(return_value=False)
    engine._is_shadow_mode = AsyncMock(return_value=True) # SHADOW active

    engine.audit_service.log = AsyncMock()
    engine._create_assignment = AsyncMock()

    result = await engine.process_incident(incident)

    # In SHADOW mode, no real assignment is persisted
    assert result is None
    engine._create_assignment.assert_not_called()

    # Decision audit trail must be recorded
    engine.audit_service.log.assert_called_once()
    args, kwargs = engine.audit_service.log.call_args
    assert args[0] == "SHADOW_ASSIGN"
    assert args[1] == "INCIDENT"
    assert kwargs["new_value"]["recommended"] == str(emp_ravi.id)

