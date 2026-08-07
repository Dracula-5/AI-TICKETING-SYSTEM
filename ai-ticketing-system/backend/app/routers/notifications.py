from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.security import get_current_user, get_current_user_ws
from app.db.database import get_db
from app.db.models import Notification, User
from app.schemas.notifications import NotificationOut, UnreadCountOut
from app.services.notification_ws import manager

router = APIRouter(prefix="/notifications", tags=["notifications"])

LIST_LIMIT = 30


@router.get("/", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .count()
    )
    return {"count": count}


@router.put("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(Notification).filter(Notification.id == notification_id).first()
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    entry.is_read = True
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.is_read == False  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()

    user = get_current_user_ws(websocket, db)
    if not user:
        await websocket.close(code=1008)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            # This channel is push-only from the server; just wait for the
            # client to disconnect (or send an occasional keepalive ping).
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
