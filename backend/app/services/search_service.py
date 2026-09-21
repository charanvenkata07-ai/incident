import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, distinct
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.incident import Incident
from app.models.assignment import IncidentAssignment
from app.models.conversation import Conversation, ConversationMember, ChatMessage
from app.models.notification import Notification
from app.models.task_template import TaskTemplate
from app.models.skill import Skill, EmployeeSkill


class SearchService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.is_admin = current_user.role in ("ADMIN", "SUPERVISOR")

    async def _get_current_employee_and_team(self) -> tuple[Optional[Employee], Optional[Team]]:
        stmt = select(Employee).where(Employee.user_id == self.current_user.id)
        res = await self.db.execute(stmt)
        emp = res.scalar_one_or_none()
        team = None
        if emp and emp.team_id:
            team = await self.db.get(Team, emp.team_id)
        return emp, team

    async def search_all(self, query: str, scope: str = "all", limit: int = 10) -> Dict[str, Any]:
        """
        Executes an authorized multi-category search across all entities.
        Normalizes query (case-insensitive, whitespace normalized).
        Enforces strict team/user level data isolation on the database level.
        """
        q = (query or "").strip()
        if not q:
            return {
                "query": "",
                "total_count": 0,
                "categories": {
                    "incidents": [],
                    "employees": [],
                    "teams": [],
                    "work": [],
                    "chat": [],
                    "notifications": [],
                    "tasks": []
                }
            }

        emp, team = await self._get_current_employee_and_team()
        pattern = f"%{q}%"

        scopes_to_run = set()
        scope_normalized = scope.lower().strip()
        if scope_normalized == "all":
            scopes_to_run = {"incidents", "employees", "teams", "work", "chat", "notifications", "tasks"}
            if self.is_admin:
                scopes_to_run.add("help")
        else:
            scopes_to_run = {scope_normalized}

        results: Dict[str, List[Dict[str, Any]]] = {
            "incidents": [],
            "employees": [],
            "teams": [],
            "work": [],
            "chat": [],
            "notifications": [],
            "tasks": [],
            "help": []
        }

        if "incidents" in scopes_to_run:
            results["incidents"] = await self.search_incidents(pattern, emp, team, limit)

        if "employees" in scopes_to_run:
            results["employees"] = await self.search_employees(pattern, emp, limit)

        if "teams" in scopes_to_run:
            results["teams"] = await self.search_teams(pattern, emp, limit)

        if "work" in scopes_to_run:
            results["work"] = await self.search_work(pattern, emp, limit)

        if "chat" in scopes_to_run:
            results["chat"] = await self.search_chat(pattern, emp, limit)

        if "notifications" in scopes_to_run:
            results["notifications"] = await self.search_notifications(pattern, limit)

        if "tasks" in scopes_to_run:
            results["tasks"] = await self.search_tasks(pattern, emp, limit)

        if "help" in scopes_to_run and self.is_admin:
            results["help"] = await self.search_help(q, limit)

        total_count = sum(len(v) for v in results.values())
        return {
            "query": q,
            "total_count": total_count,
            "categories": results
        }

    async def search_incidents(
        self, pattern: str, emp: Optional[Employee], team: Optional[Team], limit: int = 10
    ) -> List[Dict[str, Any]]:
        stmt = select(Incident)

        # Authorization filter
        if not self.is_admin:
            if not emp:
                return []
            auth_conds = []
            if team:
                auth_conds.append(Incident.assignment_group == team.name)
            auth_conds.append(Incident.assigned_to.in_([self.current_user.full_name, self.current_user.email]))
            
            # Also include incidents where employee has had an assignment
            subq_assign = select(IncidentAssignment.incident_id).where(
                or_(
                    IncidentAssignment.employee_id == emp.id,
                    IncidentAssignment.team_id == emp.team_id if emp.team_id else False
                )
            )
            auth_conds.append(Incident.id.in_(subq_assign))
            stmt = stmt.where(or_(*auth_conds))

        # Query filter
        stmt = stmt.where(
            or_(
                Incident.incident_number.ilike(pattern),
                Incident.short_description.ilike(pattern),
                Incident.description.ilike(pattern),
                Incident.category.ilike(pattern),
                Incident.priority.ilike(pattern),
                Incident.assignment_group.ilike(pattern),
                Incident.assigned_to.ilike(pattern),
                Incident.state.ilike(pattern),
                Incident.servicenow_sys_id.ilike(pattern)
            )
        ).order_by(Incident.created_at.desc()).limit(limit)

        res = await self.db.execute(stmt)
        incidents = res.scalars().all()

        items = []
        for inc in incidents:
            items.append({
                "id": str(inc.id),
                "incident_number": inc.incident_number,
                "short_description": inc.short_description,
                "priority": inc.priority,
                "state": inc.state,
                "category": inc.category,
                "assignment_group": inc.assignment_group,
                "assigned_to": inc.assigned_to,
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
                "type": "INCIDENT",
                "url": f"/incidents/{inc.id}"
            })
        return items

    async def search_employees(
        self, pattern: str, emp: Optional[Employee], limit: int = 10
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(Employee, User, Team)
            .join(User, Employee.user_id == User.id)
            .outerjoin(Team, Employee.team_id == Team.id)
            .where(User.is_active == True)
        )

        # Authorization filter: Employee only searches teammates within their team
        if not self.is_admin:
            if not emp or not emp.team_id:
                return []
            stmt = stmt.where(Employee.team_id == emp.team_id)

        # Query filter: name, code, email, or possessed skill name
        subq_skills = (
            select(EmployeeSkill.employee_id)
            .join(Skill, EmployeeSkill.skill_id == Skill.id)
            .where(Skill.name.ilike(pattern))
        )

        stmt = stmt.where(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                Employee.employee_code.ilike(pattern),
                Employee.id.in_(subq_skills)
            )
        ).order_by(User.full_name.asc()).limit(limit)

        res = await self.db.execute(stmt)
        rows = res.all()

        items = []
        for e_row, u_row, t_row in rows:
            items.append({
                "id": str(e_row.id),
                "user_id": str(u_row.id),
                "full_name": u_row.full_name,
                "email": u_row.email,
                "employee_code": e_row.employee_code,
                "team_name": t_row.name if t_row else None,
                "team_id": str(t_row.id) if t_row else None,
                "is_group_leader": e_row.is_group_leader,
                "availability_status": e_row.availability_status,
                "is_present": e_row.is_present,
                "type": "EMPLOYEE",
                "url": f"/employee/profile" if u_row.id == self.current_user.id else f"/admin/employees"
            })
        return items

    async def search_teams(
        self, pattern: str, emp: Optional[Employee], limit: int = 10
    ) -> List[Dict[str, Any]]:
        stmt = select(Team).where(Team.is_active == True)

        # Authorization filter
        if not self.is_admin:
            if not emp or not emp.team_id:
                return []
            stmt = stmt.where(Team.id == emp.team_id)

        stmt = stmt.where(
            or_(
                Team.name.ilike(pattern),
                Team.description.ilike(pattern),
                Team.work_domain.ilike(pattern)
            )
        ).order_by(Team.name.asc()).limit(limit)

        res = await self.db.execute(stmt)
        teams = res.scalars().all()

        items = []
        for t in teams:
            items.append({
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "work_domain": t.work_domain,
                "type": "TEAM",
                "url": f"/admin/groups/{t.id}/activity" if self.is_admin else "/employee/team"
            })
        return items

    async def search_work(
        self, pattern: str, emp: Optional[Employee], limit: int = 10
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(IncidentAssignment, Incident)
            .join(Incident, IncidentAssignment.incident_id == Incident.id)
        )

        # Authorization filter
        if not self.is_admin:
            if not emp:
                return []
            stmt = stmt.where(IncidentAssignment.employee_id == emp.id)

        stmt = stmt.where(
            or_(
                Incident.incident_number.ilike(pattern),
                Incident.short_description.ilike(pattern),
                IncidentAssignment.status.ilike(pattern),
                IncidentAssignment.assignment_type.ilike(pattern),
                IncidentAssignment.reason.ilike(pattern)
            )
        ).order_by(IncidentAssignment.assigned_at.desc()).limit(limit)

        res = await self.db.execute(stmt)
        rows = res.all()

        items = []
        for a_row, inc_row in rows:
            items.append({
                "id": str(a_row.id),
                "incident_id": str(inc_row.id),
                "incident_number": inc_row.incident_number,
                "short_description": inc_row.short_description,
                "status": a_row.status,
                "priority": inc_row.priority,
                "assigned_at": a_row.assigned_at.isoformat() if a_row.assigned_at else None,
                "type": "WORK",
                "url": "/my-work"
            })
        return items

    async def search_chat(
        self, pattern: str, emp: Optional[Employee], limit: int = 10
    ) -> List[Dict[str, Any]]:
        # 1. Resolve authorized conversation IDs
        auth_conv_ids = set()

        # Direct conversations where user is an active member
        direct_stmt = (
            select(ConversationMember.conversation_id)
            .join(Conversation, ConversationMember.conversation_id == Conversation.id)
            .where(
                ConversationMember.user_id == self.current_user.id,
                Conversation.type == "DIRECT"
            )
        )
        res_direct = await self.db.execute(direct_stmt)
        for cid in res_direct.scalars().all():
            auth_conv_ids.add(cid)

        # Team conversations
        if self.is_admin:
            # Admins can search all TEAM conversations
            team_convs = (await self.db.execute(select(Conversation.id).where(Conversation.type == "TEAM"))).scalars().all()
            for cid in team_convs:
                auth_conv_ids.add(cid)
            # Admins can search all ADMIN_TEAM conversations
            adm_convs = (await self.db.execute(select(Conversation.id).where(Conversation.type == "ADMIN_TEAM"))).scalars().all()
            for cid in adm_convs:
                auth_conv_ids.add(cid)
        else:
            if emp and emp.team_id:
                # Employee can access their own TEAM conversation
                t_convs = (await self.db.execute(
                    select(Conversation.id).where(
                        Conversation.type == "TEAM",
                        Conversation.team_id == emp.team_id
                    )
                )).scalars().all()
                for cid in t_convs:
                    auth_conv_ids.add(cid)

                # Employee can access ADMIN_TEAM ONLY IF active Group Leader
                if emp.is_group_leader:
                    at_convs = (await self.db.execute(
                        select(Conversation.id).where(
                            Conversation.type == "ADMIN_TEAM",
                            Conversation.team_id == emp.team_id
                        )
                    )).scalars().all()
                    for cid in at_convs:
                        auth_conv_ids.add(cid)

        if not auth_conv_ids:
            return []

        # Query chat messages
        msg_stmt = (
            select(ChatMessage, Conversation, User)
            .join(Conversation, ChatMessage.conversation_id == Conversation.id)
            .outerjoin(User, ChatMessage.sender_id == User.id)
            .where(
                ChatMessage.conversation_id.in_(auth_conv_ids),
                ChatMessage.content.ilike(pattern),
                ChatMessage.is_deleted == False
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )

        res_msg = await self.db.execute(msg_stmt)
        rows = res_msg.all()

        items = []
        for m_row, c_row, u_row in rows:
            content_display = m_row.content
            if len(content_display) > 160:
                content_display = content_display[:160] + "..."
            items.append({
                "id": str(m_row.id),
                "conversation_id": str(c_row.id),
                "conversation_type": c_row.type,
                "conversation_title": c_row.title or (c_row.type + " Chat"),
                "sender_name": u_row.full_name if u_row else "System",
                "content": content_display,
                "created_at": m_row.created_at.isoformat() if m_row.created_at else None,
                "type": "CHAT",
                "url": f"/team-chat?conversationId={c_row.id}&messageId={m_row.id}"
            })
        return items

    async def search_notifications(
        self, pattern: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        # Strictly scoped to current_user.id
        stmt = (
            select(Notification)
            .where(
                Notification.user_id == self.current_user.id,
                or_(
                    Notification.title.ilike(pattern),
                    Notification.message.ilike(pattern)
                )
            )
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )

        res = await self.db.execute(stmt)
        notifs = res.scalars().all()

        items = []
        for n in notifs:
            msg_display = n.message
            if len(msg_display) > 160:
                msg_display = msg_display[:160] + "..."
            items.append({
                "id": str(n.id),
                "title": n.title,
                "message": msg_display,
                "notification_type": n.type,
                "is_read": n.is_read,
                "incident_id": str(n.incident_id) if n.incident_id else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "type": "NOTIFICATION",
                "url": n.action_url or "/employee/notifications"
            })
        return items

    async def search_tasks(
        self, pattern: str, emp: Optional[Employee], limit: int = 10
    ) -> List[Dict[str, Any]]:
        stmt = select(TaskTemplate, Team).outerjoin(Team, TaskTemplate.team_id == Team.id).where(TaskTemplate.is_active == True)

        # Authorization filter
        if not self.is_admin:
            if not emp or not emp.team_id:
                return []
            stmt = stmt.where(TaskTemplate.team_id == emp.team_id)

        stmt = stmt.where(
            or_(
                TaskTemplate.title.ilike(pattern),
                TaskTemplate.description.ilike(pattern),
                TaskTemplate.priority.ilike(pattern)
            )
        ).order_by(TaskTemplate.title.asc()).limit(limit)

        res = await self.db.execute(stmt)
        rows = res.all()

        items = []
        for t_row, team_row in rows:
            items.append({
                "id": str(t_row.id),
                "title": t_row.title,
                "description": t_row.description,
                "priority": t_row.priority,
                "team_name": team_row.name if team_row else None,
                "type": "TASK",
                "url": "/employee/work" if not self.is_admin else "/admin/settings"
            })
        return items

    async def search_help(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        if not self.is_admin:
            return []
        from app.services.help_service import HelpService
        search_res = HelpService.search(query, limit=limit)
        items = []
        for a in search_res.get("results", []):
            items.append({
                "id": a["id"],
                "slug": a["slug"],
                "title": a["title"],
                "category_name": a["category_name"],
                "summary": a["summary"],
                "type": "HELP",
                "url": f"/admin/help?article={a['slug']}"
            })
        return items

