"""
Timezone and datetime utilities for IncidentFlow.

RULES ENFORCED:
1. Database: Timestamps are stored and loaded as timezone-aware UTC.
2. API Serialization: Datetimes are serialized as ISO-8601 strings with timezone offset (e.g. +00:00 or Z).
3. Business Timezone: Default business timezone is Asia/Kolkata (DST-free).
4. No manual +5:30 / +6:00 offset addition or subtraction.
"""
from datetime import datetime, timezone
from typing import Annotated, Optional
from zoneinfo import ZoneInfo
from pydantic import BeforeValidator, PlainSerializer
from sqlalchemy import TypeDecorator, DateTime


# ---------------------------------------------------------------------------
# SQLAlchemy TypeDecorator for consistent UTC timezone-aware datetimes
# ---------------------------------------------------------------------------
class TZDateTime(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that guarantees timezone-aware UTC datetimes
    across all database backends (PostgreSQL and SQLite).
    """
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                else:
                    value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if isinstance(value, datetime) and value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
        return value


# ---------------------------------------------------------------------------
# Pydantic v2 Annotated Types for timezone-aware serialization
# ---------------------------------------------------------------------------
def _ensure_utc_aware(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
    if isinstance(v, str):
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return v


def _serialize_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


UTCDateTime = Annotated[
    datetime,
    BeforeValidator(_ensure_utc_aware),
    PlainSerializer(_serialize_utc, return_type=str)
]

OptionalUTCDateTime = Annotated[
    Optional[datetime],
    BeforeValidator(_ensure_utc_aware),
    PlainSerializer(_serialize_utc, return_type=Optional[str])
]


def now_utc() -> datetime:
    """Current timestamp in timezone-aware UTC."""
    return datetime.now(timezone.utc)


def now_kolkata() -> datetime:
    """Current timestamp in Asia/Kolkata timezone."""
    return datetime.now(ZoneInfo("Asia/Kolkata"))
