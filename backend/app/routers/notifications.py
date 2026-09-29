import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, user_from_token
from app.db.database import SessionLocal, get_db
from app.db.models import Notification, User
from app.schemas.common import MessageOut
from app.schemas.notifications import NotificationOut, UnreadCountOut
from app.services.notification_ws import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

WS_AUTH_TIMEOUT_SECONDS = 10


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    return q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False)).count()
    return {"count": count}


@router.put("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    entry.is_read = True
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/read-all", response_model=MessageOut)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False)).update(
        {"is_read": True}, synchronize_session=False
    )
    db.commit()
    return {"message": "All notifications marked as read"}


def _authenticate(token: str | None) -> User | None:
    db = SessionLocal()
    try:
        user = user_from_token(token, db)
        if user is not None:
            db.expunge(user)
        return user
    finally:
        db.close()


@router.websocket("/ws")
async def notifications_ws(websocket: WebSocket):
    """Push channel. The client authenticates with its first message,
    {"type": "auth", "token": "<access token>"}, rather than a URL query
    parameter, so access tokens don't end up in proxy/server access logs."""
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=WS_AUTH_TIMEOUT_SECONDS)
    except Exception:
        await websocket.close(code=1008)
        return
    token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    user = await asyncio.to_thread(_authenticate, token)
    if user is None:
        await websocket.close(code=1008)
        return

    await manager.connect(user.id, websocket)
    await websocket.send_json({"type": "ready"})
    try:
        while True:
            await websocket.receive_text()  # keepalive pings; the channel is push-only
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("notification_ws_loop_failed", extra={"user_id": user.id})
    finally:
        manager.disconnect(user.id, websocket)
