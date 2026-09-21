import secrets
import string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# 32 distinct characters, avoiding confusing glyphs (e.g., 0/O, 1/I)
BASE_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

def generate_incident_number() -> str:
    """
    Generates a clean, random, enterprise-grade IncidentFlow incident ID.
    Format: INC-XXXXXXXX (e.g. INC-7K4M92XQ)
    """
    random_part = "".join(secrets.choice(BASE_CHARS) for _ in range(8))
    return f"INC-{random_part}"

async def generate_unique_incident_number(session: AsyncSession) -> str:
    """
    Guarantees server-side uniqueness against the database before persistence.
    Enforces that an existing ID is never reused.
    """
    from app.models.incident import Incident
    for _ in range(10):
        candidate = generate_incident_number()
        exists = (await session.execute(select(Incident.id).where(Incident.incident_number == candidate))).scalar_one_or_none()
        if not exists:
            return candidate
    raise RuntimeError("Failed to generate unique incident number after 10 attempts")
