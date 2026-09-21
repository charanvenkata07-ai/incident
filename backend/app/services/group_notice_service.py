"""
GroupNoticeService — sends informational notices to all members of a group.

CRITICAL SAFETY RULE:
  Sending a group notice NEVER assigns an incident, modifies incident state,
  changes ServiceNow assignment_group or assigned_to, or invokes the
  assignment engine. It is a pure notification broadcast.
"""
from __future__ import annotations

import uuid
import structlog
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.employee import Employee
from app.models.notification import Notification
from app.models.team import Team
from app.models.user import User
from app.models.integration import SyncFailure
from app.websocket.manager import ws_manager, GROUP_NOTICE_CREATED
from app.services.audit_service import AuditService

logger = structlog.get_logger()


class GroupNoticeService:
    """
    Broadcasts an informational notice to every active member of a group.

    Usage:
        svc = GroupNoticeService(db)
        result = await svc.send_to_team(
            team_id=team.id,
            title="Maintenance at 11 PM",
            message="DB maintenance window begins at 23:00.",
            incident_id=None,       # optional link to an incident
            priority=None,          # optional: "HIGH", "MEDIUM", "LOW"
            sender_id=admin_user.id # for audit trail
        )
        # result: {success: N, failed: N, email_results: [...], notification_ids: [...]}
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_to_team(
        self,
        team_id: uuid.UUID,
        title: str,
        message: str,
        incident_id: Optional[uuid.UUID] = None,
        incident_number: Optional[str] = None,
        priority: Optional[str] = None,
        sender_id: Optional[uuid.UUID] = None,
        notice_type: str = "GROUP_NOTICE",
        incident_details: Optional[dict] = None,
        full_notice_body: Optional[str] = None,
    ) -> dict:
        """
        Create notification records for every active employee in the team,
        broadcast GROUP_NOTICE_CREATED over WebSocket to each user, and
        attempt email delivery if SMTP is configured.

        Returns summary dict — NEVER raises, failures are DLQ'd.
        """
        # Fetch team
        team = await self.db.get(Team, team_id)
        if not team:
            logger.warning("group_notice.team_not_found", team_id=str(team_id))
            return {"success": 0, "failed": 0, "error": "Team not found", "notification_ids": []}

        # Fetch all active employees in the team (via User.is_active)
        emp_res = await self.db.execute(
            select(Employee).join(User, Employee.user_id == User.id).where(
                Employee.team_id == team_id,
                User.is_active == True
            )
        )
        employees = emp_res.scalars().all()

        if not employees:
            logger.info("group_notice.no_active_members", team=team.name)
            return {"success": 0, "failed": 0, "notification_ids": [], "recipients": []}

        now_utc = datetime.now(timezone.utc)
        success = 0
        failed = 0
        notification_ids = []
        email_results = []
        recipients = []

        details = incident_details or {}
        notice_text = full_notice_body or message

        for emp in employees:
            user = await self.db.get(User, emp.user_id) if emp.user_id else None
            if not user:
                continue

            try:
                # 1 — Persist notification record
                notif = Notification(
                    user_id=user.id,
                    type=notice_type,
                    title=title,
                    message=notice_text,
                    incident_id=incident_id,
                    is_read=False,
                )
                self.db.add(notif)
                # Don't flush here — let the parent session manage the transaction
                notification_ids.append(str(notif.id))

                # 2 — WebSocket broadcast (fire-and-forget; never raises)
                ws_payload = {
                    "notification_id": str(notif.id),
                    "type": notice_type,
                    "title": title,
                    "message": notice_text,
                    "team_id": str(team_id),
                    "team_name": team.name,
                    "incident_id": str(incident_id) if incident_id else None,
                    "incident_number": incident_number,
                    "issue": details.get("short_description") or title,
                    "short_description": details.get("short_description") or title,
                    "description": details.get("description") or message,
                    "priority": priority or details.get("priority") or "P3",
                    "impact": details.get("impact") or "Not provided",
                    "urgency": details.get("urgency") or "Not provided",
                    "category": details.get("category") or "Not provided",
                    "subcategory": details.get("subcategory") or "Not provided",
                    "assignment_group": team.name,
                    "configuration_item": details.get("configuration_item") or "Not provided",
                    "caller": details.get("caller") or "Not provided",
                    "location": details.get("location") or "Not provided",
                    "opened_at": details.get("opened_at") or now_utc.isoformat(),
                    "state": details.get("state") or "NEW",
                    "work_instructions": details.get("work_instructions") or "Not provided",
                    "assignment": "Assigning...",
                    "created_at": now_utc.isoformat(),
                    "is_read": False,
                }
                try:
                    await ws_manager.send_to_user(str(user.id), GROUP_NOTICE_CREATED, ws_payload)
                except Exception as ws_err:
                    logger.warning("group_notice.ws_error", user=user.email, error=str(ws_err))

                # 3 — Email (async, non-blocking, failure is DLQ'd internally)
                email_result = await self._send_email(
                    user=user,
                    title=title,
                    message=message,
                    team_name=team.name,
                    incident_number=incident_number,
                    priority=priority,
                    notif_id=notif.id,
                    now_utc=now_utc,
                )
                email_results.append(email_result)

                recipients.append({"user_id": str(user.id), "name": user.full_name, "email": user.email})
                success += 1

            except Exception as e:
                failed += 1
                logger.error("group_notice.member_failed", user=getattr(user, "email", "?"), error=str(e))

        # Audit trail
        try:
            await self.audit.log(
                action="GROUP_NOTICE_CREATED",
                entity_type="TEAM",
                entity_id=team_id,
                new_value={
                    "title": title,
                    "team": team.name,
                    "recipient_count": success,
                    "failed_count": failed,
                    "incident_number": incident_number,
                    "priority": priority,
                    "is_assignment": False,
                },
                reason=f"Group notice created and sent to {team.name} ({success} recipients)",
                actor_id=sender_id,
            )
            await self.audit.log(
                action="SEND_GROUP_NOTICE",
                entity_type="TEAM",
                entity_id=team_id,
                new_value={
                    "title": title,
                    "team": team.name,
                    "recipient_count": success,
                    "failed_count": failed,
                    "incident_number": incident_number,
                    "priority": priority,
                    # SAFETY: confirmed this is NOT an assignment
                    "is_assignment": False,
                },
                reason=f"Group notice sent to {team.name} ({success} recipients)",
                actor_id=sender_id,
            )
        except Exception as audit_err:
            logger.error("group_notice.audit_failed", error=str(audit_err))

        logger.info(
            "group_notice.sent",
            team=team.name,
            success=success,
            failed=failed,
            incident_number=incident_number,
        )

        return {
            "success": success,
            "failed": failed,
            "notification_ids": notification_ids,
            "recipients": recipients,
            "email_results": email_results,
            # SAFETY label — surfaced in API response
            "assignment_triggered": False,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_email(
        self,
        user: User,
        title: str,
        message: str,
        team_name: str,
        incident_number: Optional[str],
        priority: Optional[str],
        notif_id: uuid.UUID,
        now_utc: datetime,
    ) -> dict:
        """Attempt email delivery. Returns status dict, never raises."""
        from app.core.config import settings  # local import to avoid circular
        from app.services.email_service import EmailService  # local import

        result = {
            "user": self._mask_email(user.email),
            "provider": settings.EMAIL_PROVIDER,
            "delivered": False,
            "status": "SKIP",
        }

        if settings.EMAIL_PROVIDER == "MOCK":
            result["status"] = "MOCK"
            logger.debug("group_notice.email_mock", to=self._mask_email(user.email))
            return result

        if not settings.smtp_username or not settings.smtp_password:
            result["status"] = "CONFIG_ERROR"
            result["detail"] = "SMTP credentials not configured"
            return result

        try:
            svc = EmailService()
            subject = f"[Group Notice] {title}"
            if incident_number:
                subject = f"[{priority or 'GROUP'}] {title} — {incident_number}"

            html_body = self._build_html(
                title=title,
                message=message,
                team_name=team_name,
                incident_number=incident_number,
                priority=priority,
                recipient_name=user.full_name,
                now_utc=now_utc,
            )
            plain_body = f"{title}\n\n{message}\n\nGroup: {team_name}\n"
            if incident_number:
                plain_body += f"Incident: {incident_number}\n"

            delivered = await svc._send_smtp(
                to_address=user.email,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
            )
            result["delivered"] = delivered
            result["status"] = "DELIVERED" if delivered else "FAILED"
        except Exception as e:
            result["status"] = "FAILED"
            result["detail"] = self._safe_error(e)
            # DLQ
            try:
                self.db.add(SyncFailure(
                    operation="GROUP_NOTICE_EMAIL",
                    payload={"notif_id": str(notif_id), "team": team_name, "incident_number": incident_number},
                    error_message=self._safe_error(e),
                    retry_count=0,
                    max_retries=3,
                    status="PENDING",
                ))
            except Exception:
                pass

        return result

    def _mask_email(self, email: str) -> str:
        try:
            local, domain = email.split("@", 1)
            return f"{local[0]}***@{domain}"
        except Exception:
            return "***@***.***"

    def _safe_error(self, exc: Exception) -> str:
        from app.core.config import settings
        msg = str(exc)
        if settings.smtp_password and settings.smtp_password in msg:
            msg = msg.replace(settings.smtp_password, "***")
        return msg[:500]

    def _build_html(
        self,
        title: str,
        message: str,
        team_name: str,
        incident_number: Optional[str],
        priority: Optional[str],
        recipient_name: str,
        now_utc: datetime,
    ) -> str:
        incident_row = ""
        if incident_number:
            incident_row = f"""
            <tr>
              <td style="padding:6px 0;color:#6b7280;font-size:13px;">Incident</td>
              <td style="padding:6px 0;font-weight:600;font-size:13px;">{incident_number}</td>
            </tr>"""

        priority_row = ""
        if priority:
            priority_row = f"""
            <tr>
              <td style="padding:6px 0;color:#6b7280;font-size:13px;">Priority</td>
              <td style="padding:6px 0;font-weight:600;font-size:13px;">{priority}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;background:#f9fafb;padding:24px;">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:8px;border:1px solid #e5e7eb;padding:32px;">
  <h2 style="margin:0 0 4px;font-size:18px;color:#111827;">📢 {title}</h2>
  <p style="margin:0 0 20px;font-size:13px;color:#6b7280;">Group Notice · {team_name}</p>
  <p style="font-size:14px;color:#374151;line-height:1.6;">{message}</p>
  <table style="width:100%;border-collapse:collapse;margin-top:20px;">
    <tr>
      <td style="padding:6px 0;color:#6b7280;font-size:13px;">Group</td>
      <td style="padding:6px 0;font-weight:600;font-size:13px;">{team_name}</td>
    </tr>
    {incident_row}
    {priority_row}
    <tr>
      <td style="padding:6px 0;color:#6b7280;font-size:13px;">Sent at</td>
      <td style="padding:6px 0;font-size:13px;">{now_utc.strftime('%Y-%m-%d %H:%M UTC')}</td>
    </tr>
  </table>
  <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;">
  <p style="font-size:11px;color:#9ca3af;">
    This is a group notice. It does <strong>not</strong> assign an incident to you.<br>
    Recipient: {recipient_name}
  </p>
</div>
</body>
</html>"""
