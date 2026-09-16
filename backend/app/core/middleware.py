import time
import uuid
import contextvars
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger()
request_id_context = contextvars.ContextVar("request_id", default=None)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request_id_context.set(request_id)
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
