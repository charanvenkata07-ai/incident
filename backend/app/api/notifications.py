import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationListResponse
from app.services.notification_service import NotificationService

router = APIRouter()

@router.get("", response_model=NotificationListResponse)
@router.get("/", response_model=NotificationListResponse)
async def get_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    notif_service = NotificationService(db)
    notifs, unread_count = await notif_service.get_user_notifications(current_user.id)
    return {"notifications": notifs, "unread_count": unread_count}

@router.patch("/{id}/read")
@router.post("/{id}/read")
async def read_notification(id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        notif_uuid = uuid.UUID(id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notification ID")

    result = await db.execute(select(Notification).where(Notification.id == notif_uuid))
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        
    # IDOR check: User can only mark their own notifications as read
    if notif.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify another user's notifications"
        )

    notif_service = NotificationService(db)
    await notif_service.mark_read(notif_uuid, current_user.id)
    await db.commit()
    return {"status": "success"}

@router.post("/read-all")
async def read_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    notif_service = NotificationService(db)
    await notif_service.mark_all_read(current_user.id)
    await db.commit()
    return {"status": "success"}
