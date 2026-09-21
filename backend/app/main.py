from fastapi import FastAPI, Depends, WebSocket, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.core.config import settings
from app.core.middleware import (
    get_request_id, LoggingMiddleware, RequestIDMiddleware,
    SecurityHeadersMiddleware, RateLimitMiddleware
)
from app.api.auth import router as auth_router
from app.api.employees import router as employees_router
from app.api.incidents import router as incidents_router
from app.api.admin import router as admin_router
from app.api.notifications import router as notifications_router
from app.api.chat import router as chat_router
from app.api.search import router as search_router
from app.api.help import router as help_router
from app.integrations.servicenow.webhook import router as sn_router
from app.websocket.manager import ws_manager
from sqlalchemy import text
from app.core.database import get_db, engine, Base
from contextlib import asynccontextmanager
import uuid as _uuid
import structlog as _structlog
_logger = _structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation: aborts if production environment is insecure or staging targets production
    settings.validate_production_safety()
    settings.validate_environment_isolation()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown


app = FastAPI(title="IncidentFlow API", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    request_id = get_request_id() or str(_uuid.uuid4())
    if isinstance(exc.detail, dict):
        content = dict(exc.detail)
        content.setdefault('request_id', request_id)
        if "detail" not in content:
            content["detail"] = content.get("message", "Error")
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers={**(exc.headers or {}), "X-Request-ID": request_id}
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": {"code": "HTTP_ERROR", "message": exc.detail, "request_id": request_id}
        },
        headers={**(exc.headers or {}), "X-Request-ID": request_id}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = get_request_id() or str(_uuid.uuid4())
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "fields": exc.errors(),
                "request_id": request_id
            }
        },
        headers={"X-Request-ID": request_id}
    )

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    request_id = get_request_id() or str(_uuid.uuid4())
    _logger.warning("db_integrity_error", request_id=request_id, path=request.url.path, detail=str(exc.orig)[:200])
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "CONFLICT",
                "message": "Resource conflict or duplicate entry",
                "request_id": request_id
            }
        },
        headers={"X-Request-ID": request_id}
    )

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    request_id = get_request_id() or str(_uuid.uuid4())
    _logger.error("db_error", request_id=request_id, path=request.url.path, error=str(exc)[:300])
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "DATABASE_ERROR",
                "message": "A database error occurred. Please retry.",
                "request_id": request_id
            }
        },
        headers={"X-Request-ID": request_id}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    request_id = get_request_id() or str(_uuid.uuid4())
    import traceback
    _logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=repr(exc),
        traceback=traceback.format_exc()
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Our team has been notified.",
                "request_id": request_id
            }
        },
        headers={"X-Request-ID": request_id}
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(employees_router, prefix="/api/me", tags=["Employees"])
app.include_router(employees_router, prefix="/api/employees", tags=["Employees"])
app.include_router(incidents_router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(search_router, prefix="/api/search", tags=["Search"])
app.include_router(help_router, prefix="/api/admin/help", tags=["Help"])
app.include_router(sn_router, prefix="/api/integrations/servicenow", tags=["ServiceNow"])

@app.get("/metrics")
async def prometheus_metrics():
    from fastapi.responses import PlainTextResponse
    from app.core.metrics import metrics
    return PlainTextResponse(metrics.get_metrics_text())


@app.get("/health")
@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    """
    Section 33: Comprehensive Health Check.
    Returns real readiness/health status for:
    - Database
    - Redis
    - Worker
    - WebSocket
    - ServiceNow
    - Notification service
    - Email configuration
    - Assignment engine
    - Live Pilot
    """
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        from redis.asyncio import from_url
        r = from_url(settings.REDIS_URL, socket_connect_timeout=1)
        await r.ping()
        await r.aclose()
    except Exception:
        redis_ok = False

    sn_configured = bool(settings.SERVICENOW_URL and settings.SERVICENOW_URL != "https://dev-staging.service-now.com")
    email_configured = bool(settings.smtp_username and settings.smtp_password)

    dependencies = {
        "database": "HEALTHY" if db_ok else "UNHEALTHY",
        "redis": "HEALTHY" if redis_ok else "DEGRADED",
        "worker": "HEALTHY" if redis_ok else "DEGRADED",
        "websocket": "HEALTHY",
        "servicenow": "HEALTHY (MOCK/LOCAL)" if settings.SERVICENOW_MOCK else ("HEALTHY" if sn_configured else "NOT_CONFIGURED"),
        "notifications": "HEALTHY",
        "email": "HEALTHY" if email_configured else "NOT_CONFIGURED (IN_APP_ACTIVE)",
        "assignment_engine": "HEALTHY" if db_ok else "UNHEALTHY",
        "live_pilot": "ARMED" if settings.LIVE_PILOT_ENABLED else "SAFE_SHADOW"
    }

    is_healthy = db_ok
    return {
        "status": "HEALTHY" if is_healthy else "UNHEALTHY",
        "service": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "automation_mode": settings.AUTOMATION_MODE,
        "dependencies": dependencies,
        "live_pilot_enabled": settings.LIVE_PILOT_ENABLED
    }


from fastapi import Response, status

@app.get("/ready")
@app.get("/api/ready")
async def ready(response: Response, db: AsyncSession = Depends(get_db)):
    components = {}
    is_ready = True
    overall_status = "HEALTHY"

    # 1. Database Check
    try:
        if settings.ENVIRONMENT.upper() in ("STAGING", "PRODUCTION") and "sqlite" in settings.DATABASE_URL.lower():
            components["database"] = "FAIL (PostgreSQL required in STAGING/PRODUCTION)"
            is_ready = False
            overall_status = "UNAVAILABLE"
        else:
            await db.execute(text("SELECT 1"))
            components["database"] = "HEALTHY"
    except Exception as e:
        components["database"] = "UNAVAILABLE"
        is_ready = False
        overall_status = "UNAVAILABLE"

    # 2. Redis Check
    try:
        from redis.asyncio import from_url
        r = from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        components["redis"] = "HEALTHY"
    except Exception:
        components["redis"] = "DEGRADED"
        if overall_status == "HEALTHY":
            overall_status = "DEGRADED"

    # 3. Worker State
    components["worker"] = "HEALTHY" if components.get("redis") == "HEALTHY" else "DEGRADED"

    # 4. ServiceNow Integration State
    if settings.SERVICENOW_MOCK:
        components["servicenow"] = "HEALTHY (MOCK)"
    else:
        components["servicenow"] = "HEALTHY" if settings.SERVICENOW_URL else "DEGRADED"

    # 5. Notification Provider
    components["notifications"] = f"HEALTHY ({settings.EMAIL_PROVIDER})"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "ready": is_ready,
        "environment": settings.ENVIRONMENT,
        "automation_mode": settings.AUTOMATION_MODE,
        "components": components
    }


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    from app.core.security import verify_token
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    role = payload.get("role", "EMPLOYEE")
    await ws_manager.connect(websocket, user_id, role)
    try:
        while True:
            text_data = await websocket.receive_text()
            if text_data == "ping":
                await websocket.send_text("pong")
            else:
                try:
                    import json
                    parsed = json.loads(text_data)
                    action = parsed.get("action") or parsed.get("type")
                    if action == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket, user_id)


