from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.core.security import get_current_user, require_role
from app.db.database import get_db
from app.db.models import NegotiationSession, Order, Product, User, Vendor
from app.schemas.analytics import AdminAnalyticsOut, VendorAnalyticsOut

router = APIRouter(prefix="/analytics", tags=["analytics"])

ANALYTICS_CACHE_TTL = 30


def _negotiation_success_rate(db: Session, filters) -> tuple[int, int, float]:
    total = db.query(func.count(NegotiationSession.id)).filter(*filters).scalar() or 0
    accepted = db.query(func.count(NegotiationSession.id)).filter(
        *filters, NegotiationSession.status == "accepted"
    ).scalar() or 0
    rate = round(accepted / total * 100, 1) if total else 0.0
    return total, accepted, rate


@router.get("/vendor", response_model=VendorAnalyticsOut)
def vendor_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="No vendor profile for this account")

    cache_key = f"analytics:vendor:{vendor.id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    total_products = db.query(func.count(Product.id)).filter(Product.vendor_id == vendor.id).scalar() or 0
    total_views = db.query(func.coalesce(func.sum(Product.views_count), 0)).filter(
        Product.vendor_id == vendor.id
    ).scalar() or 0
    total_orders = db.query(func.count(Order.id)).filter(Order.vendor_id == vendor.id).scalar() or 0
    total_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0.0)).filter(
        Order.vendor_id == vendor.id, Order.status != "cancelled"
    ).scalar() or 0.0

    total_neg, accepted_neg, rate = _negotiation_success_rate(db, [NegotiationSession.vendor_id == vendor.id])

    top_products = (
        db.query(Product.id, Product.title, Product.views_count)
        .filter(Product.vendor_id == vendor.id)
        .order_by(Product.views_count.desc())
        .limit(5)
        .all()
    )

    result = VendorAnalyticsOut(
        total_products=total_products,
        total_views=int(total_views),
        total_orders=total_orders,
        total_revenue=float(total_revenue),
        total_negotiations=total_neg,
        accepted_negotiations=accepted_neg,
        negotiation_success_rate_pct=rate,
        top_products=[{"id": p[0], "title": p[1], "views_count": p[2]} for p in top_products],
    ).model_dump()

    cache_set(cache_key, result, ANALYTICS_CACHE_TTL)
    return result


@router.get("/admin", response_model=AdminAnalyticsOut)
def admin_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["admin"])

    cache_key = f"analytics:admin:{current_user.tenant_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    tenant_id = current_user.tenant_id
    total_vendors = db.query(func.count(Vendor.id)).filter(Vendor.tenant_id == tenant_id).scalar() or 0
    total_products = db.query(func.count(Product.id)).filter(Product.tenant_id == tenant_id).scalar() or 0
    total_views = db.query(func.coalesce(func.sum(Product.views_count), 0)).filter(
        Product.tenant_id == tenant_id
    ).scalar() or 0
    total_orders = db.query(func.count(Order.id)).filter(Order.tenant_id == tenant_id).scalar() or 0
    total_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0.0)).filter(
        Order.tenant_id == tenant_id, Order.status != "cancelled"
    ).scalar() or 0.0

    total_neg, accepted_neg, rate = _negotiation_success_rate(db, [NegotiationSession.tenant_id == tenant_id])

    top_vendors_rows = (
        db.query(Vendor.id, Vendor.shop_name, func.coalesce(func.sum(Order.total_price), 0.0).label("revenue"))
        .outerjoin(Order, Order.vendor_id == Vendor.id)
        .filter(Vendor.tenant_id == tenant_id)
        .group_by(Vendor.id, Vendor.shop_name)
        .order_by(func.coalesce(func.sum(Order.total_price), 0.0).desc())
        .limit(5)
        .all()
    )

    result = AdminAnalyticsOut(
        total_vendors=total_vendors,
        total_products=total_products,
        total_views=int(total_views),
        total_orders=total_orders,
        total_revenue=float(total_revenue),
        total_negotiations=total_neg,
        accepted_negotiations=accepted_neg,
        negotiation_success_rate_pct=rate,
        top_vendors=[{"id": r[0], "shop_name": r[1], "revenue": float(r[2])} for r in top_vendors_rows],
    ).model_dump()

    cache_set(cache_key, result, ANALYTICS_CACHE_TTL)
    return result
