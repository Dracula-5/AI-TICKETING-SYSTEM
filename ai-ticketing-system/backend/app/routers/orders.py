from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import NegotiationSession, Order, Product, User, Vendor
from app.schemas.orders import OrderCreate, OrderOut
from app.core.security import get_current_user, require_role
from app.services.notification_service import notify

router = APIRouter(prefix="/orders", tags=["orders"])

ALLOWED_ORDER_STATUS = ["pending", "confirmed", "shipped", "completed", "cancelled"]


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["customer"])

    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product or product.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Product not found")

    unit_price = product.price
    negotiation_session_id = None

    if payload.negotiation_session_id is not None:
        session = db.query(NegotiationSession).filter(
            NegotiationSession.id == payload.negotiation_session_id
        ).first()
        if not session or session.tenant_id != current_user.tenant_id:
            raise HTTPException(status_code=404, detail="Negotiation session not found")
        if session.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="This negotiation does not belong to you")
        if session.product_id != product.id:
            raise HTTPException(status_code=400, detail="Negotiation session does not match this product")
        if session.status != "accepted":
            raise HTTPException(status_code=400, detail="Negotiation has not been accepted yet")
        unit_price = session.current_offer_price
        negotiation_session_id = session.id

    if product.stock_quantity < payload.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock available")

    product.stock_quantity -= payload.quantity

    order = Order(
        tenant_id=current_user.tenant_id,
        product_id=product.id,
        customer_id=current_user.id,
        vendor_id=product.vendor_id,
        negotiation_session_id=negotiation_session_id,
        quantity=payload.quantity,
        unit_price=unit_price,
        total_price=round(unit_price * payload.quantity, 2),
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    await notify(
        db, order.tenant_id, product.vendor.user_id,
        type_="order_placed",
        title="New order received",
        message=f"{current_user.name} ordered {payload.quantity} x '{product.title}' ({product.currency} {order.total_price:.2f})",
        link="/vendor/dashboard",
    )

    return order


@router.get("/my", response_model=list[OrderOut])
def list_my_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["customer"])
    return (
        db.query(Order)
        .filter(Order.customer_id == current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )


@router.get("/vendor/received", response_model=list[OrderOut])
def list_vendor_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="No vendor profile for this account")

    return (
        db.query(Order)
        .filter(Order.vendor_id == vendor.id)
        .order_by(Order.created_at.desc())
        .all()
    )


@router.put("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    new_status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    if new_status not in ALLOWED_ORDER_STATUS:
        raise HTTPException(status_code=400, detail=f"status must be one of {ALLOWED_ORDER_STATUS}")

    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="No vendor profile for this account")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.vendor_id != vendor.id:
        raise HTTPException(status_code=403, detail="Not your order")

    order.status = new_status
    db.commit()
    db.refresh(order)

    await notify(
        db, order.tenant_id, order.customer_id,
        type_="order_status_changed",
        title="Order update",
        message=f"Your order for '{order.product.title}' is now {new_status}",
        link="/orders",
    )

    return order
