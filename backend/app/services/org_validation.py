"""
IncidentFlow — Organization Structure Validation Service
Enforces the authoritative business invariant:
- Exactly 15 active teams
- Exactly 10 active employees per active team
- Exactly 150 active employees total
- Every employee has a unique Employee ID
"""
import structlog
from typing import Dict, Any, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.team import Team
from app.models.employee import Employee
from app.models.user import User

logger = structlog.get_logger()

EXPECTED_TEAMS_COUNT = 15
EXPECTED_MEMBERS_PER_TEAM = 10
EXPECTED_TOTAL_EMPLOYEES = 150


class OrgValidationError(ValueError):
    """Raised when organization structure violates the 15x10=150 invariant."""
    pass


async def validate_organization_structure(session: AsyncSession) -> Dict[str, Any]:
    """
    Validates:
    1. Exactly 15 active teams exist.
    2. Each active team has exactly 10 active employees.
    3. Total active employees is exactly 150.
    4. All active Employee codes are unique and non-empty.
    """
    # 1. Active teams
    teams_stmt = select(Team).where(Team.is_active == True).order_by(Team.name)
    teams_res = await session.execute(teams_stmt)
    active_teams = list(teams_res.scalars().all())

    if len(active_teams) != EXPECTED_TEAMS_COUNT:
        msg = f"Organization structure violation: expected exactly {EXPECTED_TEAMS_COUNT} active teams, found {len(active_teams)}."
        logger.error("org_validation_failed_team_count", expected=EXPECTED_TEAMS_COUNT, actual=len(active_teams))
        raise OrgValidationError(msg)

    # 2. Per-team member counts & total count
    all_active_codes: List[str] = []
    team_breakdown = {}

    for team in active_teams:
        emps_stmt = (
            select(Employee)
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.team_id == team.id,
                User.is_active == True
            )
            .order_by(Employee.employee_code.asc(), Employee.id.asc())
        )
        emps_res = await session.execute(emps_stmt)
        team_emps = list(emps_res.scalars().all())

        if len(team_emps) != EXPECTED_MEMBERS_PER_TEAM:
            msg = (
                f"Team '{team.name}' violation: expected exactly {EXPECTED_MEMBERS_PER_TEAM} active employees, "
                f"found {len(team_emps)}."
            )
            logger.error("org_validation_failed_member_count", team=team.name, expected=EXPECTED_MEMBERS_PER_TEAM, actual=len(team_emps))
            raise OrgValidationError(msg)

        codes = [e.employee_code for e in team_emps if e.employee_code]
        if len(codes) != EXPECTED_MEMBERS_PER_TEAM or len(set(codes)) != EXPECTED_MEMBERS_PER_TEAM:
            msg = f"Team '{team.name}' contains duplicate or missing employee codes."
            raise OrgValidationError(msg)

        all_active_codes.extend(codes)
        team_breakdown[team.name] = {
            "team_id": str(team.id),
            "members_count": len(team_emps),
            "codes": codes
        }

    # 3. Total active employee count
    if len(all_active_codes) != EXPECTED_TOTAL_EMPLOYEES:
        msg = f"Organization violation: expected exactly {EXPECTED_TOTAL_EMPLOYEES} active employees, found {len(all_active_codes)}."
        raise OrgValidationError(msg)

    # 4. Global code uniqueness
    if len(set(all_active_codes)) != EXPECTED_TOTAL_EMPLOYEES:
        msg = "Organization violation: duplicate Employee IDs detected across teams."
        raise OrgValidationError(msg)

    logger.info(
        "org_validation_success",
        teams_count=len(active_teams),
        total_employees=len(all_active_codes)
    )

    return {
        "status": "valid",
        "teams_count": len(active_teams),
        "total_employees": len(all_active_codes),
        "teams": team_breakdown
    }
