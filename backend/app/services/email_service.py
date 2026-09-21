"""
IncidentFlow Email Service
==========================
Handles real SMTP email delivery with:
  - Async STARTTLS on port 587 (aiosmtplib)
  - Connection timeout (10 s connect, 30 s total)
  - Exponential-backoff retry  (up to MAX_RETRIES attempts)
  - DLQ recording in sync_failures table on persistent failure
  - Secret redaction — SMTP_PASSWORD is NEVER logged
  - Rich HTML + plain-text multipart body
  - Failure-safe: exceptions are caught and recorded; they never bubble up
    to interrupt the assignment pipeline

ENVIRONMENT / MODE
  EMAIL_PROVIDER=MOCK   → log-only, no socket opened
  EMAIL_PROVIDER=SMTP   → real delivery via STARTTLS

SAFETY
  Credentials are read exclusively from environment variables via settings.
  No credential is ever written to logs, responses, or the database.
"""

from __future__ import annotations

import asyncio
import uuid
import structlog
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = structlog.get_logger()

# ── constants ──────────────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0          # seconds; doubles each attempt
CONNECT_TIMEOUT = 10            # seconds — SMTP connect
COMMAND_TIMEOUT = 30            # seconds — SMTP commands / data transfer


# ── helpers ───────────────────────────────────────────────────────────────────

def _redact(value: str) -> str:
    """Return '***REDACTED***' for any non-empty secret string."""
    return "***REDACTED***" if value else "(empty)"


def _priority_label(priority: str) -> str:
    labels = {
        "1": "P1 – Critical",
        "P1": "P1 – Critical",
        "2": "P2 – High",
        "P2": "P2 – High",
        "3": "P3 – Moderate",
        "P3": "P3 – Moderate",
        "4": "P4 – Low",
        "P4": "P4 – Low",
    }
    return labels.get(str(priority).strip(), str(priority))


def _build_email_body(
    incident_number: str,
    short_description: str,
    priority: str,
    assignment_group: str,
    assigned_to: str,
    work_instructions: Optional[str],
    assigned_at: str,
    incident_url: str,
) -> tuple[str, str]:
    """
    Returns (html_body, plain_body).
    Uses ONLY the data passed in — nothing is invented.
    """
    pri_label = _priority_label(priority)
    wi_section_plain = (
        f"\nYOUR TASK / Work Instructions:\n{work_instructions}\n"
        if work_instructions
        else ""
    )
    wi_section_html = (
        f"""
        <tr>
          <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
            <span style="color:#6b7280;font-size:13px;">YOUR TASK / Work Instructions</span><br>
            <span style="white-space:pre-wrap;font-size:14px;">{work_instructions}</span>
          </td>
        </tr>"""
        if work_instructions
        else ""
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Incident Assignment</title></head>
<body style="font-family:Arial,sans-serif;background:#f3f4f6;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;
                    box-shadow:0 1px 3px rgba(0,0,0,.1);">
        <!-- Header -->
        <tr>
          <td style="background:#1d4ed8;padding:24px 32px;">
            <span style="color:#fff;font-size:20px;font-weight:bold;">🔔 IncidentFlow</span>
            <span style="color:#93c5fd;font-size:14px;margin-left:12px;">Incident Assigned to You</span>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:32px;">
            <p style="color:#111827;font-size:16px;margin:0 0 24px;">
              Hello,<br><br>
              An incident has been assigned to you via IncidentFlow.
            </p>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                  <span style="color:#6b7280;font-size:13px;">Incident Number</span><br>
                  <strong style="font-size:16px;color:#111827;">{incident_number}</strong>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                  <span style="color:#6b7280;font-size:13px;">Short Description</span><br>
                  <span style="font-size:14px;color:#111827;">{short_description}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                  <span style="color:#6b7280;font-size:13px;">Priority</span><br>
                  <span style="font-size:14px;color:#dc2626;font-weight:600;">{pri_label}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                  <span style="color:#6b7280;font-size:13px;">Assignment Group</span><br>
                  <span style="font-size:14px;color:#111827;">{assignment_group}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                  <span style="color:#6b7280;font-size:13px;">Assigned To</span><br>
                  <span style="font-size:14px;color:#111827;">{assigned_to}</span>
                </td>
              </tr>
              {wi_section_html}
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e5e7eb;">
                  <span style="color:#6b7280;font-size:13px;">Assigned At</span><br>
                  <span style="font-size:14px;color:#111827;">{assigned_at}</span>
                </td>
              </tr>
            </table>

            <div style="text-align:center;margin-top:32px;">
              <a href="{incident_url}"
                 style="background:#1d4ed8;color:#fff;padding:12px 28px;
                        border-radius:6px;text-decoration:none;font-size:15px;
                        font-weight:600;">
                Open Incident in IncidentFlow →
              </a>
            </div>

            <p style="color:#9ca3af;font-size:12px;margin-top:32px;text-align:center;">
              This is an automated notification from IncidentFlow (SHADOW mode — no production mutations).
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    plain = f"""IncidentFlow — Incident Assigned to You
=======================================

Incident Number   : {incident_number}
Short Description : {short_description}
Priority          : {pri_label}
Assignment Group  : {assignment_group}
Assigned To       : {assigned_to}{wi_section_plain}
Assigned At       : {assigned_at}

Open Incident: {incident_url}

---
This is an automated notification from IncidentFlow.
"""
    return html, plain


# ── public API ────────────────────────────────────────────────────────────────

class EmailService:
    """Async email delivery service.  One instance per request/task."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── main entry points ──────────────────────────────────────────────────────

    async def send_assignment_email(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        incident_number: str,
        short_description: str,
        priority: str,
        assignment_group: str,
        assigned_to: str,
        work_instructions: Optional[str],
        assigned_at: datetime,
        incident_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Send a real assignment notification email.

        Returns True if delivered, False if queued to DLQ or mocked.
        Never raises — all failures are caught and DLQ'd.
        """
        subject = f"[IncidentFlow] Incident {incident_number} assigned to you"
        assigned_at_str = assigned_at.strftime("%Y-%m-%d %H:%M UTC") if assigned_at else "—"
        incident_url = f"{settings.APP_BASE_URL.rstrip('/')}/work/{incident_number}"

        html_body, plain_body = _build_email_body(
            incident_number=incident_number,
            short_description=short_description,
            priority=priority,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            work_instructions=work_instructions,
            assigned_at=assigned_at_str,
            incident_url=incident_url,
        )

        return await self._dispatch(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            incident_id=incident_id,
            context_label=f"assignment:{incident_number}",
        )

    async def send_test_email(
        self,
        *,
        recipient_email: str,
        incident_number: str = "TEST-0001",
        short_description: str = "IncidentFlow SMTP connectivity test",
        priority: str = "P3",
        assignment_group: str = "Analytics – MDM L3",
        assigned_to: str = "Test Engineer",
        work_instructions: Optional[str] = "Verify SMTP delivery is functioning correctly.",
    ) -> dict:
        """
        Send a single test email and return a detailed result dict.
        Used by POST /api/admin/integrations/servicenow/test-email.
        """
        subject = f"[IncidentFlow] SMTP Test — {incident_number}"
        incident_url = f"{settings.APP_BASE_URL.rstrip('/')}/work/{incident_number}"
        html_body, plain_body = _build_email_body(
            incident_number=incident_number,
            short_description=short_description,
            priority=priority,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            work_instructions=work_instructions,
            assigned_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            incident_url=incident_url,
        )

        result = {
            "provider": settings.EMAIL_PROVIDER,
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "tls": settings.SMTP_TLS,
            "from": settings.smtp_from_address,
            "to": recipient_email,
            "to_masked": _mask_email(recipient_email),
            "subject": subject,
            "smtp_password_configured": bool(settings.smtp_password),
            "smtp_username_configured": bool(settings.smtp_username),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if settings.EMAIL_PROVIDER == "MOCK":
            logger.info(
                "test_email_mock_dispatched",
                recipient=recipient_email,
                subject=subject,
            )
            result.update({"status": "MOCK", "delivered": False, "detail": "EMAIL_PROVIDER=MOCK; no socket opened"})
            return result

        if not settings.smtp_username or not settings.smtp_password:
            result.update({
                "status": "CONFIG_ERROR",
                "delivered": False,
                "detail": "SMTP_USERNAME or SMTP_PASSWORD not configured",
            })
            return result

        ok, error = await self._smtp_send_with_retry(
            recipient_email=recipient_email,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
        )
        if ok:
            result.update({"status": "DELIVERED", "delivered": True, "detail": "SMTP server accepted message"})
        else:
            result.update({"status": "FAILED", "delivered": False, "detail": error or "Unknown SMTP error"})
        return result

    # ── internal dispatch ──────────────────────────────────────────────────────

    async def _dispatch(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        subject: str,
        html_body: str,
        plain_body: str,
        incident_id: Optional[uuid.UUID],
        context_label: str,
    ) -> bool:
        if settings.EMAIL_PROVIDER == "MOCK":
            logger.info(
                "email_mock_dispatched",
                provider="MOCK",
                recipient=recipient_email,
                subject=subject,
                context=context_label,
            )
            return False  # not actually delivered

        if not settings.smtp_username or not settings.smtp_password:
            logger.warning(
                "email_skipped_no_credentials",
                context=context_label,
                username_set=bool(settings.smtp_username),
                password_set=bool(settings.smtp_password),
            )
            return False

        ok, error = await self._smtp_send_with_retry(
            recipient_email=recipient_email,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
        )

        if ok:
            logger.info(
                "email_delivered",
                provider="SMTP",
                recipient=recipient_email,
                context=context_label,
            )
            return True
        else:
            logger.error(
                "email_delivery_failed_after_retries",
                recipient=recipient_email,
                context=context_label,
                error=error,
            )
            await self._record_dlq(
                recipient_email=recipient_email,
                subject=subject,
                error_message=error or "Unknown SMTP error",
                incident_id=incident_id,
            )
            return False

    # ── SMTP with retry ────────────────────────────────────────────────────────

    async def _smtp_send_with_retry(
        self,
        *,
        recipient_email: str,
        subject: str,
        html_body: str,
        plain_body: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Attempt SMTP delivery up to MAX_RETRIES times with exponential backoff.
        Returns (success, error_message).
        SMTP_PASSWORD is NEVER included in logs or error messages.
        """
        last_error: Optional[str] = None
        delay = RETRY_BASE_DELAY

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self._smtp_send_once(
                    recipient_email=recipient_email,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                )
                return True, None
            except Exception as exc:
                # Redact any accidentally included credentials from error strings
                raw = str(exc)
                safe_error = _safe_error_message(raw)
                last_error = safe_error
                logger.warning(
                    "smtp_send_attempt_failed",
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                    host=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    error=safe_error,
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(delay)
                    delay *= 2  # exponential backoff

        return False, last_error

    async def _smtp_send_once(
        self,
        *,
        recipient_email: str,
        subject: str,
        html_body: str,
        plain_body: str,
    ) -> None:
        """Send one SMTP message via STARTTLS using stdlib smtplib (asyncio.to_thread). Raises on any error."""
        import smtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_address}>"
        msg["To"] = recipient_email
        msg["X-Mailer"] = "IncidentFlow/1.0"

        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        def _sync_send():
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=CONNECT_TIMEOUT) as server:
                server.ehlo()
                if settings.SMTP_TLS:
                    server.starttls()
                    server.ehlo()
                server.login(settings.smtp_username, settings.smtp_password)  # never logged
                server.send_message(msg)

        await asyncio.to_thread(_sync_send)

    # ── DLQ recording ─────────────────────────────────────────────────────────

    async def _record_dlq(
        self,
        *,
        recipient_email: str,
        subject: str,
        error_message: str,
        incident_id: Optional[uuid.UUID],
    ) -> None:
        """Record failed email into sync_failures (DLQ) table."""
        try:
            from app.models.integration import SyncFailure

            failure = SyncFailure(
                incident_id=incident_id,
                operation="EMAIL_DELIVERY",
                payload={
                    "recipient": recipient_email,
                    "subject": subject,
                    "provider": settings.EMAIL_PROVIDER,
                    "smtp_host": settings.SMTP_HOST,
                    "smtp_port": settings.SMTP_PORT,
                    # password intentionally omitted
                },
                error_message=error_message,
                retry_count=MAX_RETRIES,
                max_retries=MAX_RETRIES,
                next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                status="FAILED",
            )
            self.db.add(failure)
            await self.db.flush()
            logger.info(
                "email_failure_recorded_in_dlq",
                recipient=recipient_email,
                incident_id=str(incident_id) if incident_id else None,
            )
        except Exception as dlq_exc:
            logger.error("email_dlq_record_failed", error=str(dlq_exc))


# ── SMTP probe (connection test only) ─────────────────────────────────────────

async def probe_smtp_connection() -> dict:
    """
    Test SMTP connectivity, TLS, and authentication without sending a message.
    Returns a structured result dict safe to return from an API endpoint.
    Credentials are never included in the result.
    """
    result = {
        "provider": settings.EMAIL_PROVIDER,
        "smtp_host": settings.SMTP_HOST,
        "smtp_port": settings.SMTP_PORT,
        "tls": settings.SMTP_TLS,
        "username_configured": bool(settings.smtp_username),
        "password_configured": bool(settings.smtp_password),
        "connected": False,
        "tls_negotiated": False,
        "authenticated": False,
        "error": None,
    }

    if settings.EMAIL_PROVIDER == "MOCK":
        result["error"] = "EMAIL_PROVIDER=MOCK; no connection attempted"
        return result

    if not settings.smtp_username or not settings.smtp_password:
        result["error"] = "SMTP_USERNAME or SMTP_PASSWORD not configured"
        return result

    try:
        import smtplib

        connected_flag = [False]
        tls_flag = [False]
        auth_flag = [False]

        def _sync_probe():
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=CONNECT_TIMEOUT)
            try:
                server.ehlo()
                connected_flag[0] = True
                if settings.SMTP_TLS:
                    server.starttls()
                    server.ehlo()
                    tls_flag[0] = True
                server.login(settings.smtp_username, settings.smtp_password)  # never logged
                auth_flag[0] = True
                server.quit()
            finally:
                try:
                    server.close()
                except Exception:
                    pass

        await asyncio.wait_for(
            asyncio.to_thread(_sync_probe),
            timeout=CONNECT_TIMEOUT + COMMAND_TIMEOUT,
        )
        result["connected"] = connected_flag[0]
        result["tls_negotiated"] = tls_flag[0]
        result["authenticated"] = auth_flag[0]

    except Exception as exc:
        safe = _safe_error_message(str(exc))
        result["error"] = safe
        logger.warning(
            "smtp_probe_failed",
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            error=safe,
        )

    return result


# ── utilities ──────────────────────────────────────────────────────────────────

def _mask_email(email: str) -> str:
    """Returns user@d****n.com style masked email."""
    try:
        user, domain = email.rsplit("@", 1)
        parts = domain.rsplit(".", 1)
        masked_domain = parts[0][0] + "*" * (len(parts[0]) - 1) + "." + parts[1] if len(parts) == 2 else domain
        return f"{user}@{masked_domain}"
    except Exception:
        return "***@***.***"


def _safe_error_message(raw: str) -> str:
    """Strip any occurrence of the SMTP password from an error string."""
    pwd = settings.smtp_password
    if pwd and pwd in raw:
        raw = raw.replace(pwd, "***REDACTED***")
    return raw
