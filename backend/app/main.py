from fastapi import FastAPI, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.middleware import get_request_id, LoggingMiddleware, RequestIDMiddleware
from app.api.auth import router as auth_router
from app.api.employees import router as employees_router
from app.api.incidents import router as incidents_router
from app.api.admin import router as admin_router
from app.api.notifications import router as notifications_router
from app.integrations.servicenow.webhook import router as sn_router
from app.websocket.manager import ws_manager
from sqlalchemy import text
from app.core.database import get_db, engine
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: could create tables here if not using alembic
    yield
    # Shutdown

app = FastAPI(title="IncidentFlow API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(employees_router, prefix="/api/me", tags=["Employees"])
app.include_router(incidents_router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(sn_router, prefix="/api/integrations/servicenow", tags=["ServiceNow"])

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/ready")
async def ready(db = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ready" if db_status == "ok" else "error", "database": db_status}

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

    await ws_manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:
        await ws_manager.disconnect(websocket, user_id)

