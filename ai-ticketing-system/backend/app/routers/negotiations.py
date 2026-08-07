from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import NegotiationMessage, NegotiationSession, Product, User
from app.schemas.negotiations import (
    NegotiationStart,
    NegotiationMessageOut,
    NegotiationSessionOut,
    NegotiationSessionSummaryOut,
)
from app.core.security import get_current_user, get_current_user_ws, require_role
from app.services.negotiation_ai import generate_vendor_response
from app.services.negotiation_ws import manager
from app.services.notification_service import notify
from app.db.models import Vendor

router = APIRouter(prefix="/negotiations", tags=["negotiations"])

WS_ALLOWED_TYPES = ("text", "offer", "accept", "reject")


def _load_session_for_tenant(session_id: int, db: Session, current_user: User) -> NegotiationSession:
    session = db.query(NegotiationSession).filter(NegotiationSession.id == session_id).first()
    if not session or session.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Negotiation session not found")
    return session


def _negotiation_counterpart(session: NegotiationSession, sender_role: str) -> int:
    """The user who did NOT send this message -- customer for vendor/ai_assistant senders, vendor for customer senders."""
    return session.vendor.user_id if sender_role == "customer" else session.customer_id


def _authorize_participant(session: NegotiationSession, current_user: User) -> str:
    """Returns the sender_role for current_user on this session, or raises 403."""
    if session.customer_id == current_user.id:
        return "customer"
    if session.vendor.user_id == current_user.id:
        return "vendor"
    if current_user.role == "admin":
        return "admin"
    raise HTTPException(status_code=403, detail="Not a participant in this negotiation")


def _ordered_messages(db: Session, session_id: int) -> list[NegotiationMessage]:
    return (
        db.query(NegotiationMessage)
        .filter(NegotiationMessage.session_id == session_id)
        .order_by(NegotiationMessage.created_at.asc(), NegotiationMessage.id.asc())
        .all()
    )


@router.post("/", response_model=NegotiationSessionOut, status_code=status.HTTP_201_CREATED)
async def start_negotiation(
    payload: NegotiationStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["customer"])

    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product or product.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != "active":
        raise HTTPException(status_code=400, detail="Product is not available for negotiation")

    session = NegotiationSession(
        tenant_id=current_user.tenant_id,
        product_id=product.id,
        customer_id=current_user.id,
        vendor_id=product.vendor_id,
        status="open",
        current_offer_price=payload.amount,
    )
    db.add(session)
    db.flush()

    db.add(NegotiationMessage(
        session_id=session.id,
        sender_role="customer",
        sender_user_id=current_user.id,
        message_type="offer",
        amount=payload.amount,
        text_content=payload.message,
    ))
    db.commit()
    db.refresh(session)

    if product.auto_negotiate_enabled:
        await generate_vendor_response(db, session, product, product.vendor, _ordered_messages(db, session.id))
        db.refresh(session)

    await notify(
        db, session.tenant_id, product.vendor.user_id,
        type_="negotiation_started",
        title="New price negotiation",
        message=f"{current_user.name} offered {product.currency} {payload.amount:.2f} for '{product.title}'",
        link=f"/negotiation/{session.id}",
    )

    return session


@router.get("/vendor/inbox", response_model=list[NegotiationSessionSummaryOut])
def vendor_inbox(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_role(current_user, ["vendor"])
    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="No vendor profile for this account")

    return (
        db.query(NegotiationSession)
        .filter(NegotiationSession.vendor_id == vendor.id)
        .order_by(NegotiationSession.created_at.desc())
        .all()
    )


@router.get("/{session_id}", response_model=NegotiationSessionOut)
def get_negotiation(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _load_session_for_tenant(session_id, db, current_user)
    _authorize_participant(session, current_user)
    return session


@router.post("/{session_id}/accept", response_model=NegotiationSessionOut)
async def accept_negotiation(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = _load_session_for_tenant(session_id, db, current_user)
    role = _authorize_participant(session, current_user)
    if role not in ("customer", "vendor"):
        raise HTTPException(status_code=403, detail="Only the customer or vendor can accept")
    if session.status != "open":
        raise HTTPException(status_code=400, detail=f"Session already {session.status}")

    priced = [m for m in _ordered_messages(db, session.id) if m.amount is not None]
    if not priced:
        raise HTTPException(status_code=400, detail="No offer to accept yet")
    latest = priced[-1]

    db.add(NegotiationMessage(
        session_id=session.id,
        sender_role=role,
        sender_user_id=current_user.id,
        message_type="accept",
        amount=latest.amount,
    ))
    session.status = "accepted"
    session.current_offer_price = latest.amount
    session.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(session)

    await notify(
        db, session.tenant_id, _negotiation_counterpart(session, role),
        type_="negotiation_accepted",
        title="Deal accepted",
        message=f"Negotiation accepted at {session.product.currency} {latest.amount:.2f}",
        link=f"/negotiation/{session.id}",
    )

    return session


@router.websocket("/{session_id}/ws")
async def negotiation_ws(websocket: WebSocket, session_id: int, db: Session = Depends(get_db)):
    await websocket.accept()

    user = get_current_user_ws(websocket, db)
    if not user:
        await websocket.close(code=1008)
        return

    session = db.query(NegotiationSession).filter(NegotiationSession.id == session_id).first()
    if not session or session.tenant_id != user.tenant_id:
        await websocket.close(code=1008)
        return

    try:
        sender_role = _authorize_participant(session, user)
    except HTTPException:
        await websocket.close(code=1008)
        return
    if sender_role not in ("customer", "vendor"):
        await websocket.close(code=1008)
        return

    product = db.query(Product).filter(Product.id == session.product_id).first()
    vendor = session.vendor

    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type not in WS_ALLOWED_TYPES:
                continue

            amount = data.get("amount")
            if msg_type in ("accept", "reject") and amount is None:
                priced = [m for m in _ordered_messages(db, session.id) if m.amount is not None]
                amount = priced[-1].amount if priced else None

            entry = NegotiationMessage(
                session_id=session.id,
                sender_role=sender_role,
                sender_user_id=user.id,
                message_type=msg_type,
                amount=amount,
                text_content=data.get("text"),
            )
            db.add(entry)

            if msg_type == "accept" and amount is not None:
                session.status = "accepted"
                session.current_offer_price = amount
                session.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)

            db.commit()
            db.refresh(entry)
            await manager.broadcast(
                session_id, NegotiationMessageOut.model_validate(entry).model_dump(mode="json")
            )
            await notify(
                db, session.tenant_id, _negotiation_counterpart(session, sender_role),
                type_="negotiation_message",
                title=f"New message on '{product.title}'",
                message=entry.text_content or (f"Offer: {product.currency} {entry.amount:.2f}" if entry.amount is not None else msg_type),
                link=f"/negotiation/{session.id}",
            )

            if (
                sender_role == "customer"
                and product.auto_negotiate_enabled
                and session.status == "open"
                and msg_type in ("text", "offer")
            ):
                ai_entry = await generate_vendor_response(
                    db, session, product, vendor, _ordered_messages(db, session.id)
                )
                if ai_entry:
                    await manager.broadcast(
                        session_id, NegotiationMessageOut.model_validate(ai_entry).model_dump(mode="json")
                    )
                    await notify(
                        db, session.tenant_id, session.customer_id,
                        type_="negotiation_message",
                        title=f"Vendor responded on '{product.title}'",
                        message=ai_entry.text_content or (f"Offer: {product.currency} {ai_entry.amount:.2f}" if ai_entry.amount is not None else ai_entry.message_type),
                        link=f"/negotiation/{session.id}",
                    )
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
