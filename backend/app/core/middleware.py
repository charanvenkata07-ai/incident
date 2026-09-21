import os
import time
import uuid
import contextvars
import threading
from collections import defaultdict
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import structlog

logger = structlog.get_logger()
request_id_context = contextvars.ContextVar("request_id", default=None)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_id = request.headers.get("X-Request-ID", "").strip()
        if client_id and len(client_id) <= 64 and client_id.replace('-', '').replace('_', '').isalnum():
            request_id = client_id
        else:
            request_id = str(uuid.uuid4())
        request_id_context.set(request_id)
        request.state.request_id = request_id
        try:
            structlog.contextvars.bind_contextvars(request_id=request_id)
        except Exception:
            pass
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        request_id = request_id_context.get()
        
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration=duration,
        )
        
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enforces enterprise security headers to mitigate clickjacking, MIME sniffing,
    and cross-site scripting vulnerabilities.
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
        
        from app.core.config import settings
        if request.url.scheme == "https" or settings.ENVIRONMENT.upper() in ("PRODUCTION", "STAGING"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory rate limiter protecting sensitive API endpoints:
    - /api/auth/login: Prevents brute-force credential stuffing (20 req / min)
    - /api/admin/integrations/servicenow/test-connection: Prevents outbound flooding (15 req / min)
    - /api/admin/automation/mode: Prevents rapid state toggling (10 req / min)
    - /api/integrations/servicenow/incidents: Webhook ingress rate limit (150 req / min)
    """
    RATE_LIMITS = {
        "/api/auth/login": (20, 60),
        "/api/admin/integrations/servicenow/test-connection": (15, 60),
        "/api/admin/automation/mode": (10, 60),
        "/api/integrations/servicenow/incidents": (150, 60),
    }

    def __init__(self, app):
        super().__init__(app)
        self._history = defaultdict(list)
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("TESTING"):
            return await call_next(request)

        path = request.url.path.rstrip("/")
        limit_config = self.RATE_LIMITS.get(path)

        if limit_config and request.method == "POST":
            max_requests, window_seconds = limit_config
            client_ip = request.client.host if request.client else "unknown"
            key = f"{client_ip}:{path}"
            now = time.time()

            with self._lock:
                timestamps = [ts for ts in self._history[key] if now - ts < window_seconds]
                if len(timestamps) >= max_requests:
                    logger.warning("rate_limit_exceeded", ip=client_ip, path=path)
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please retry later."},
                        headers={"Retry-After": str(window_seconds)}
                    )
                timestamps.append(now)
                self._history[key] = timestamps

        return await call_next(request)

def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_context.get()

