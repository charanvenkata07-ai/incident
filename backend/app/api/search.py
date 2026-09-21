from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.search_service import SearchService

router = APIRouter()


@router.get("")
@router.get("/")
async def global_search(
    q: str = Query("", description="Search term"),
    scope: str = Query("all", description="Search scope (all, employees, teams, incidents, work, chat, notifications, tasks)"),
    limit: int = Query(10, ge=1, le=50, description="Max results per category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified, authorized search endpoint across IncidentFlow.
    Respects strict role, team, and participant boundaries.
    Never returns passwords, tokens, or unauthorized records.
    """
    clean_q = (q or "").strip()
    if not clean_q:
        return {
            "query": "",
            "total_count": 0,
            "categories": {
                "incidents": [],
                "employees": [],
                "teams": [],
                "work": [],
                "chat": [],
                "notifications": [],
                "tasks": []
            }
        }

    search_svc = SearchService(db, current_user)
    return await search_svc.search_all(query=clean_q, scope=scope, limit=limit)
