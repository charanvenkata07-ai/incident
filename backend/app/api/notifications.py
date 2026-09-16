from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/")
async def get_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"notifications": [], "unread_count": 0}

@router.patch("/{id}/read")
async def read_notification(id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"status": "success"}

@router.post("/read-all")
async def read_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"status": "success"}
