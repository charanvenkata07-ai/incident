import os
import re
import uuid
from datetime import date, timezone, datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.team import Team
from app.models.employee import Employee
from app.models.skill import Skill, EmployeeSkill
from app.models.assignment import IncidentAssignment
from app.models.incident import Incident
from app.models.shift import Shift, ShiftAssignment
from app.models.notification import Notification
from app.schemas.employee import (
    EmployeeResponse, AvailabilityUpdate, UserProfileResponse, UserProfileUpdate,
    TeamMemberDetail, MyTeamDetailResponse
)
from app.schemas.incident import IncidentBrief
from app.services.audit_service import AuditService
from app.websocket.manager import (
    ws_manager,
    CHAT_PRESENCE_CHANGED,
    EMPLOYEE_STATUS_CHANGED,
    GROUP_ACTIVITY_EVENT,
    PROFILE_UPDATED,
    TEAM_MEMBER_UPDATED
)

router = APIRouter()

AVATARS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "avatars")
os.makedirs(AVATARS_DIR, exist_ok=True)

async def _build_profile_dict(db: AsyncSession, user: User) -> dict:
    emp_stmt = select(Employee).where(Employee.user_id == user.id)
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()
    
    team_name = None
    skills_list = []
    active_count = 0
    shift_data = None

    if emp:
        if emp.team_id:
            team_obj = await db.get(Team, emp.team_id)
            if team_obj:
                team_name = team_obj.name

        skills_query = (
            select(Skill)
            .join(EmployeeSkill, EmployeeSkill.skill_id == Skill.id)
            .where(EmployeeSkill.employee_id == emp.id)
        )
        skills_res = await db.execute(skills_query)
        skills_list = [
            {"id": s.id, "name": s.name, "description": s.description, "is_active": s.is_active}
            for s in skills_res.scalars().all()
        ]

        count_query = select(func.count(IncidentAssignment.id)).where(
            IncidentAssignment.employee_id == emp.id,
            IncidentAssignment.is_active == True
        )
        count_res = await db.execute(count_query)
        active_count = count_res.scalar() or 0

        # Fetch today's shift
        today = datetime.now(timezone.utc).date()
        shift_stmt = select(ShiftAssignment).where(
            ShiftAssignment.employee_id == emp.id,
            ShiftAssignment.date == today,
            ShiftAssignment.is_active == True
        )
        s_assignments = (await db.execute(shift_stmt)).scalars().all()
        if s_assignments:
            now_time = datetime.now(timezone.utc).time()
            chosen_sh = None
            for sa in s_assignments:
                sh_cand = await db.get(Shift, sa.shift_id)
                if sh_cand:
                    if sh_cand.is_overnight:
                        if now_time >= sh_cand.start_time or now_time < sh_cand.end_time:
                            chosen_sh = sh_cand
                            break
                    else:
                        if sh_cand.start_time <= now_time < sh_cand.end_time:
                            chosen_sh = sh_cand
                            break
            if not chosen_sh and s_assignments:
                chosen_sh = await db.get(Shift, s_assignments[0].shift_id)
            if chosen_sh:
                shift_data = {
                    "id": str(chosen_sh.id),
                    "name": chosen_sh.name,
                    "start_time": str(chosen_sh.start_time),
                    "end_time": str(chosen_sh.end_time),
                    "timezone": chosen_sh.timezone,
                    "is_overnight": chosen_sh.is_overnight
                }

    return {
        "id": emp.id if emp else user.id,
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "phone": user.phone,
        "bio": user.bio,
        "timezone": user.timezone or "Asia/Kolkata",
        "notification_preferences": user.notification_preferences,
        "chat_preferences": user.chat_preferences,
        "team_id": emp.team_id if emp else None,
        "team_name": team_name,
        "employee_code": emp.employee_code if emp else None,
        "is_group_leader": emp.is_group_leader if emp else False,
        "availability_status": emp.availability_status if emp else "OFFLINE",
        "is_present": emp.is_present if emp else False,
        "skills": skills_list,
        "active_incident_count": active_count,
        "shift": shift_data
    }

@router.get("", response_model=UserProfileResponse)
@router.get("/", response_model=UserProfileResponse)
@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    data = await _build_profile_dict(db, current_user)
    return data


@router.get("/work", response_model=list[IncidentBrief])
async def get_work(status: str = None, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.audit import AuditLog
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        return []
    
    query = select(Incident, IncidentAssignment).join(
        IncidentAssignment, Incident.id == IncidentAssignment.incident_id
    ).where(
        IncidentAssignment.employee_id == emp.id,
        IncidentAssignment.is_active == True
    )
    if status:
        query = query.where(IncidentAssignment.status == status.upper())
        
    result = await db.execute(query)
    rows = result.all()
    assigned_incidents: list[IncidentBrief] = []
    assigned_ids = set()

    for inc, asgn in rows:
        assigned_incidents.append(
            IncidentBrief(
                id=inc.id,
                incident_number=inc.incident_number,
                short_description=inc.short_description,
                priority=inc.priority,
                state=inc.state,
                assignment_group=inc.assignment_group,
                work_instructions=inc.work_instructions,
                assigned_employee_name=current_user.full_name,
                assignment_status=asgn.status,
                assigned_at=asgn.assigned_at
            )
        )
        assigned_ids.add(inc.id)

    # In SHADOW mode, also expose recommended synthetic tickets so engineers can experience the workflow
    shadow_query = select(AuditLog).where(
        AuditLog.action == 'SHADOW_ASSIGN',
        AuditLog.entity_type == 'INCIDENT'
    ).order_by(AuditLog.created_at.desc())
    shadow_logs = (await db.execute(shadow_query)).scalars().all()

    for slog in shadow_logs:
        if slog.new_value and slog.new_value.get("recommended") == str(emp.id):
            if slog.entity_id and slog.entity_id not in assigned_ids:
                inc = await db.get(Incident, slog.entity_id)
                if inc and (not status or inc.state == status.upper()):
                    assigned_incidents.append(
                        IncidentBrief(
                            id=inc.id,
                            incident_number=inc.incident_number,
                            short_description=inc.short_description,
                            priority=inc.priority,
                            state=inc.state,
                            assignment_group=inc.assignment_group,
                            work_instructions=inc.work_instructions,
                            assigned_employee_name=current_user.full_name,
                            assignment_status=inc.state,
                            assigned_at=inc.created_at
                        )
                    )
                    assigned_ids.add(inc.id)

    return assigned_incidents

@router.get("/shift")
async def get_shift(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        return None
        
    today = datetime.now(timezone.utc).date()
    query = select(ShiftAssignment).where(
        ShiftAssignment.employee_id == emp.id,
        ShiftAssignment.date == today,
        ShiftAssignment.is_active == True
    )
    assignments = (await db.execute(query)).scalars().all()
    if not assignments:
        return None

    assignment = assignments[0]
    sh = await db.get(Shift, assignment.shift_id)
    now_time = datetime.now(timezone.utc).time()
    for a in assignments:
        sh_cand = await db.get(Shift, a.shift_id)
        if sh_cand:
            if sh_cand.is_overnight:
                if now_time >= sh_cand.start_time or now_time < sh_cand.end_time:
                    assignment = a
                    sh = sh_cand
                    break
            else:
                if sh_cand.start_time <= now_time < sh_cand.end_time:
                    assignment = a
                    sh = sh_cand
                    break

    if not sh:
        return None

    # Count active incidents for this employee
    count_query = select(IncidentAssignment).where(
        IncidentAssignment.employee_id == emp.id,
        IncidentAssignment.is_active == True
    )
    count_res = await db.execute(count_query)
    active_count = len(count_res.scalars().all())

    # Fetch team name without lazy loading
    team_name = None
    if emp.team_id:
        team_obj = await db.get(Team, emp.team_id)
        if team_obj:
            team_name = team_obj.name

    # Fetch skills without lazy loading
    skills_query = (
        select(Skill)
        .join(EmployeeSkill, EmployeeSkill.skill_id == Skill.id)
        .where(EmployeeSkill.employee_id == emp.id)
    )
    skills_res = await db.execute(skills_query)
    skills_list = [{"id": s.id, "name": s.name} for s in skills_res.scalars().all()]

    return {
        "id": assignment.id,
        "date": str(assignment.date),
        "is_active": assignment.is_active,
        "shift": {
            "id": sh.id,
            "name": sh.name,
            "start_time": str(sh.start_time),
            "end_time": str(sh.end_time),
            "timezone": sh.timezone,
            "is_overnight": sh.is_overnight,
            "is_active": sh.is_active
        },
        "employee": {
            "id": emp.id,
            "user_id": emp.user_id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "team_id": emp.team_id,
            "team_name": team_name,
            "employee_code": emp.employee_code,
            "availability_status": emp.availability_status,
            "is_present": emp.is_present,
            "skills": skills_list,
            "active_incident_count": active_count
        }
    }


@router.get("/notifications")
async def get_notifications(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Notification).where(Notification.user_id == current_user.id).order_by(desc(Notification.created_at))
    result = await db.execute(query)
    notifs = result.scalars().all()
    unread_count = sum(1 for n in notifs if not n.is_read)
    return {"notifications": notifs, "unread_count": unread_count}

@router.patch("/availability")
async def update_availability(req: AvailabilityUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    old_status = emp.availability_status
    emp.availability_status = req.status
    
    audit_service = AuditService(db)
    await audit_service.log('AVAILABILITY_CHANGE', 'EMPLOYEE', emp.id, old_value={'status': old_status}, new_value={'status': req.status}, actor_id=current_user.id)
    
    await db.commit()
    return {"status": "success", "new_status": req.status}


@router.patch("/profile", response_model=UserProfileResponse)
async def update_profile(
    req: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    emp_stmt = select(Employee).where(Employee.user_id == current_user.id)
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()

    old_values = {
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "bio": current_user.bio,
        "timezone": current_user.timezone,
        "availability_status": emp.availability_status if emp else None
    }

    if req.full_name is not None and req.full_name.strip():
        current_user.full_name = req.full_name.strip()
    if req.phone is not None:
        current_user.phone = req.phone.strip() if req.phone else None
    if req.bio is not None:
        current_user.bio = req.bio.strip() if req.bio else None
    if req.timezone is not None and req.timezone.strip():
        current_user.timezone = req.timezone.strip()
    if req.notification_preferences is not None:
        current_user.notification_preferences = req.notification_preferences
    if req.chat_preferences is not None:
        current_user.chat_preferences = req.chat_preferences

    if req.availability_status is not None and emp:
        emp.availability_status = req.availability_status

    current_user.updated_at = datetime.now(timezone.utc)
    if emp:
        emp.updated_at = datetime.now(timezone.utc)

    audit_service = AuditService(db)
    await audit_service.log(
        'PROFILE_UPDATED',
        'USER',
        current_user.id,
        old_value=old_values,
        new_value={
            "full_name": current_user.full_name,
            "phone": current_user.phone,
            "bio": current_user.bio,
            "timezone": current_user.timezone,
            "availability_status": emp.availability_status if emp else None
        },
        actor_id=current_user.id
    )

    await db.commit()
    await db.refresh(current_user)

    # Broadcast real-time profile update to team members and admins
    profile_payload = {
        "user_id": str(current_user.id),
        "employee_id": str(emp.id) if emp else str(current_user.id),
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
        "phone": current_user.phone,
        "bio": current_user.bio,
        "timezone": current_user.timezone,
        "availability_status": emp.availability_status if emp else "OFFLINE",
        "is_present": emp.is_present if emp else False,
        "is_group_leader": emp.is_group_leader if emp else False,
        "team_id": str(emp.team_id) if emp and emp.team_id else None
    }

    if emp and emp.team_id:
        await ws_manager.broadcast_to_team(str(emp.team_id), PROFILE_UPDATED, profile_payload)
        await ws_manager.broadcast_to_team(str(emp.team_id), TEAM_MEMBER_UPDATED, profile_payload)
    await ws_manager.broadcast_to_admins(PROFILE_UPDATED, profile_payload)

    return await _build_profile_dict(db, current_user)


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Validate MIME type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type {file.content_type}. Only JPG, PNG, WEBP, and GIF images are allowed."
        )

    content = await file.read()
    max_bytes = settings.MAX_PROFILE_IMAGE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Avatar file exceeds max size of {settings.MAX_PROFILE_IMAGE_SIZE_MB}MB"
        )

    safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename or "avatar.png")
    unique_filename = f"{uuid.uuid4().hex}_{safe_name}"
    file_path = os.path.join(AVATARS_DIR, unique_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    avatar_url = f"/api/me/avatar/file/{unique_filename}"
    current_user.avatar_url = avatar_url
    current_user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)

    emp_stmt = select(Employee).where(Employee.user_id == current_user.id)
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()

    profile_payload = {
        "user_id": str(current_user.id),
        "employee_id": str(emp.id) if emp else str(current_user.id),
        "full_name": current_user.full_name,
        "avatar_url": current_user.avatar_url,
        "phone": current_user.phone,
        "bio": current_user.bio,
        "timezone": current_user.timezone,
        "availability_status": emp.availability_status if emp else "OFFLINE",
        "is_present": emp.is_present if emp else False,
        "is_group_leader": emp.is_group_leader if emp else False,
        "team_id": str(emp.team_id) if emp and emp.team_id else None
    }

    if emp and emp.team_id:
        await ws_manager.broadcast_to_team(str(emp.team_id), PROFILE_UPDATED, profile_payload)
        await ws_manager.broadcast_to_team(str(emp.team_id), TEAM_MEMBER_UPDATED, profile_payload)
    await ws_manager.broadcast_to_admins(PROFILE_UPDATED, profile_payload)

    return {"status": "success", "avatar_url": avatar_url}


@router.get("/avatar/file/{filename}")
async def get_avatar_file(filename: str):
    clean_filename = os.path.basename(filename)
    file_path = os.path.join(AVATARS_DIR, clean_filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Avatar image not found")
    return FileResponse(file_path)


@router.get("/teammates/{teammate_user_id}", response_model=UserProfileResponse)
async def get_teammate_profile(
    teammate_user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    target_user = await db.get(User, teammate_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Teammate not found")

    # Authorization: employees can only view same-team members (or admins if they are group leader)
    if current_user.role == 'EMPLOYEE' and str(current_user.id) != str(teammate_user_id):
        req_emp_res = await db.execute(select(Employee).where(Employee.user_id == current_user.id))
        req_emp = req_emp_res.scalar_one_or_none()

        tgt_emp_res = await db.execute(select(Employee).where(Employee.user_id == target_user.id))
        tgt_emp = tgt_emp_res.scalar_one_or_none()

        if target_user.role in ('ADMIN', 'SUPERVISOR'):
            # Only group leaders may view admin profiles
            if not req_emp or not req_emp.is_group_leader:
                raise HTTPException(status_code=403, detail="Only Group Leaders can view Admin profiles")
        else:
            # Must be same team
            if not req_emp or not tgt_emp or str(req_emp.team_id) != str(tgt_emp.team_id):
                raise HTTPException(status_code=403, detail="You can only view profiles of your own team members")

    data = await _build_profile_dict(db, target_user)

    # Scope private preferences: only return to self
    if str(current_user.id) != str(target_user.id):
        data.pop('notification_preferences', None)
        data.pop('chat_preferences', None)

    return data


@router.get("/team", response_model=MyTeamDetailResponse)
async def get_my_team(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Section 4: Real operational team details for authenticated employee.
    Derives employee identity strictly from authentication token.
    Returns:
    - id, name, description, work_domain, servicenow_group_id
    - group_leader (with badge, contact, presence)
    - members (all active team members with status, shift, presence)
    - member_count, online_count, available_count
    """
    emp_stmt = select(Employee).where(Employee.user_id == current_user.id)
    emp = (await db.execute(emp_stmt)).scalar_one_or_none()
    
    # If user is admin/supervisor without employee row, find first active team
    team_id = emp.team_id if emp else None
    if not team_id:
        if current_user.role in ("ADMIN", "SUPERVISOR"):
            first_team = (await db.execute(select(Team).where(Team.is_active == True).order_by(Team.name))).scalars().first()
            if first_team:
                team_id = first_team.id
        if not team_id:
            raise HTTPException(status_code=404, detail="Employee is not assigned to any operational team")

    team = await db.get(Team, team_id)
    if not team or not team.is_active:
        raise HTTPException(status_code=404, detail="Team not found or inactive")

    # Fetch all active employees belonging to this team
    members_stmt = (
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.team_id == team.id,
            User.is_active == True
        )
        .order_by(Employee.is_group_leader.desc(), User.full_name.asc())
    )
    rows = (await db.execute(members_stmt)).all()

    today = datetime.now(timezone.utc).date()
    now_time = datetime.now(timezone.utc).time()

    member_details = []
    group_leader_detail = None

    for m_emp, m_user in rows:
        # 1. Active assignments
        assign_count_stmt = select(func.count(IncidentAssignment.id)).where(
            IncidentAssignment.employee_id == m_emp.id,
            IncidentAssignment.is_active == True
        )
        active_assigns = (await db.execute(assign_count_stmt)).scalar() or 0

        # 2. Shift info
        shift_stmt = (
            select(ShiftAssignment)
            .where(
                ShiftAssignment.employee_id == m_emp.id,
                ShiftAssignment.date == today,
                ShiftAssignment.is_active == True
            )
        )
        s_assignments = (await db.execute(shift_stmt)).scalars().all()
        shift_name = None
        shift_hours = None
        if s_assignments:
            chosen_sh = None
            for sa in s_assignments:
                sh_cand = await db.get(Shift, sa.shift_id)
                if sh_cand:
                    if sh_cand.is_overnight:
                        if now_time >= sh_cand.start_time or now_time < sh_cand.end_time:
                            chosen_sh = sh_cand
                            break
                    else:
                        if sh_cand.start_time <= now_time < sh_cand.end_time:
                            chosen_sh = sh_cand
                            break
            if not chosen_sh and s_assignments:
                chosen_sh = await db.get(Shift, s_assignments[0].shift_id)
            if chosen_sh:
                shift_name = chosen_sh.name
                shift_hours = f"{chosen_sh.start_time.strftime('%H:%M')} - {chosen_sh.end_time.strftime('%H:%M')} {chosen_sh.timezone}"

        # 3. Skills
        skills_query = (
            select(Skill.name)
            .join(EmployeeSkill, EmployeeSkill.skill_id == Skill.id)
            .where(EmployeeSkill.employee_id == m_emp.id)
        )
        skills_list = list((await db.execute(skills_query)).scalars().all())

        m_detail = TeamMemberDetail(
            id=m_emp.id,
            employee_id=m_emp.id,
            user_id=m_user.id,
            full_name=m_user.full_name,
            email=m_user.email,
            avatar_url=m_user.avatar_url,
            role=m_user.role,
            is_group_leader=bool(m_emp.is_group_leader),
            employee_code=m_emp.employee_code,
            is_present=bool(m_emp.is_present),
            availability_status=m_emp.availability_status or "OFFLINE",
            current_shift_name=shift_name,
            current_shift_hours=shift_hours,
            active_assignments=active_assigns,
            skills=skills_list
        )
        member_details.append(m_detail)
        if m_emp.is_group_leader and not group_leader_detail:
            group_leader_detail = m_detail

    # Fallback group leader if none explicitly flagged
    if not group_leader_detail and member_details:
        group_leader_detail = member_details[0]

    return MyTeamDetailResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        work_domain=team.work_domain,
        servicenow_group_id=team.servicenow_group_id,
        group_leader=group_leader_detail,
        members=member_details,
        member_count=len(member_details),
        online_count=sum(1 for m in member_details if m.is_present),
        available_count=sum(1 for m in member_details if m.availability_status == "AVAILABLE")
    )

