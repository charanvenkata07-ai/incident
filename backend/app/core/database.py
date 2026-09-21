from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

import os

db_url = settings.DATABASE_URL
# Fallback to local SQLite if running locally without PostgreSQL service running
if "postgresql" in db_url and not os.environ.get("FORCE_POSTGRES"):
    try:
        import socket
        # Test if localhost:5432 is responding
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('127.0.0.1', 5432))
        sock.close()
        if result != 0:
            db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "incidentflow.db"))
            db_url = f"sqlite+aiosqlite:///{db_path}"
    except Exception:
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "incidentflow.db"))
        db_url = f"sqlite+aiosqlite:///{db_path}"

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PGUUID, "sqlite")
def compile_pguuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

import sys
from sqlalchemy.pool import NullPool

engine_kwargs = {"echo": settings.DEBUG}
if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("TESTING"):
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(db_url, **engine_kwargs)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
