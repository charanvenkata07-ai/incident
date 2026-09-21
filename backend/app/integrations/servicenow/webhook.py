import uuid
import hmac
import json
from datetime import datetime, timezone
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.config import settings
from app.schemas.servicenow import ServiceNowIncidentPayload
from app.models.integration import IntegrationEvent
from app.models.incident import Incident
from app.services.incident_service import IncidentService
from app.services.assignment_engine import AssignmentEngine
from app.integrations.servicenow.mapper import ServiceNowMapper

logger = structlog.get_logger()
router = APIRouter()

MAX_WEBHOOK_PAYLOAD_BYTES = 1_048_576  # 1 MB

@router.post("/incidents")
async def receive_incident(
    payload: ServiceNowIncidentPayload,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    x_servicenow_secret: str | None = Header(None, alias="X-ServiceNow-Secret"),
    authorization: str | None = Header(None)
):
    """
    Ingests incidents dispatched from ServiceNow Business Rules / Webhooks.
    Enforces authentication, replay protection, deduplication, and zero incident loss.
    """
    # 0. Payload Size Guard (Denial-of-Service prevention)
    if request:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_WEBHOOK_PAYLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Payload exceeds maximum limit of 1MB"
            )

    # 1. Authentication Check (Timing-attack resistant comparison)
    configured_secret = settings.SERVICENOW_WEBHOOK_SECRET
    if configured_secret:
        auth_token = None
        if authorization and authorization.startswith("Bearer "):
            auth_token = authorization.split("Bearer ", 1)[1].strip()

        provided_secret = x_servicenow_secret or auth_token
        if not provided_secret or not hmac.compare_digest(provided_secret, configured_secret):
            logger.warning("servicenow_webhook_unauthorized", provided=bool(provided_secret))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid ServiceNow Webhook Secret"
            )
    elif settings.ENVIRONMENT.upper() in ("PRODUCTION", "STAGING"):
        logger.error("servicenow_webhook_rejected_no_server_secret")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured on server"
        )

    if hasattr(payload, "model_dump"):
        payload_dict = payload.model_dump(mode="json")
    elif hasattr(payload, "dict"):
        payload_dict = json.loads(payload.json())
    else:
        payload_dict = json.loads(json.dumps(dict(payload), default=str))
    sys_id = payload_dict.get("sys_id")
    number = payload_dict.get("number") or payload_dict.get("incident_number") or "UNKNOWN"
    mod_count = payload_dict.get("sys_mod_count", 0) or 0
    idempotency_key = f"sn:{sys_id}:{mod_count or number}" if sys_id else f"sn:num:{number}"

    # 2. Replay Protection & Deduplication via stable idempotency_key
    stmt_existing = select(IntegrationEvent).where(IntegrationEvent.idempotency_key == idempotency_key)
    existing_event_res = await db.execute(stmt_existing)
    existing_event = existing_event_res.scalar_one_or_none()
    if isinstance(existing_event, IntegrationEvent):
        logger.info("servicenow_duplicate_webhook_deduplicated", idempotency_key=idempotency_key, incident=number)
        inc_stmt = select(Incident).where(
            (Incident.servicenow_sys_id == sys_id) | (Incident.incident_number == number)
        )
        inc_res = await db.execute(inc_stmt)
        existing_inc = inc_res.scalar_one_or_none()
        return {
            "status": "processed",
            "incident_number": existing_inc.incident_number if isinstance(existing_inc, Incident) else number,
            "sys_id": existing_inc.servicenow_sys_id if isinstance(existing_inc, Incident) else sys_id,
            "is_new": False,
            "event_id": str(existing_event.id),
            "deduplicated": True
        }

    event_id = uuid.uuid4()
    integration_event = IntegrationEvent(
        id=event_id,
        event_type="INCIDENT_INGEST",
        source="SERVICENOW",
        payload=payload_dict,
        incident_number=number,
        idempotency_key=idempotency_key,
        status="RECEIVED"
    )
    db.add(integration_event)
    try:
        await db.flush()
    except Exception as flush_err:
        await db.rollback()
        logger.info("servicenow_concurrent_duplicate_caught", idempotency_key=idempotency_key, error=str(flush_err))
        inc_stmt = select(Incident).where(
            (Incident.servicenow_sys_id == sys_id) | (Incident.incident_number == number)
        )
        inc_res = await db.execute(inc_stmt)
        existing_inc = inc_res.scalar_one_or_none()
        return {
            "status": "processed",
            "incident_number": existing_inc.incident_number if existing_inc else number,
            "sys_id": existing_inc.servicenow_sys_id if existing_inc else sys_id,
            "is_new": False,
            "event_id": str(event_id),
            "deduplicated": True
        }

    try:
        # 3. Create or update incident
        incident_service = IncidentService(db)
        incident, is_new = await incident_service.create_or_update_from_servicenow(payload)

        # 4. Trigger assignment engine if new ticket
        if is_new:
            engine = AssignmentEngine(db)
            await engine.process_incident(incident)

        integration_event.status = "PROCESSED"
        integration_event.processed_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "servicenow_webhook_ingested",
            incident_number=incident.incident_number,
            sys_id=incident.servicenow_sys_id,
            is_new=is_new
        )

        return {
            "status": "processed",
            "incident_number": incident.incident_number,
            "sys_id": incident.servicenow_sys_id,
            "is_new": is_new,
            "event_id": str(event_id)
        }
    except Exception as ex:
        await db.rollback()
        # Record failure into an isolated transaction to preserve DLQ observability
        try:
            fail_event = IntegrationEvent(
                id=uuid.uuid4(),
                event_type="INCIDENT_INGEST_FAILED",
                source="SERVICENOW",
                payload=payload_dict,
                incident_number=number,
                status="FAILED",
                error_message=str(ex)
            )
            db.add(fail_event)
            await db.commit()
        except Exception:
            pass

        logger.error("servicenow_webhook_processing_error", error=str(ex), number=number)
        return {
            "status": "error_logged",
            "incident_number": number,
            "error": str(ex)
        }
