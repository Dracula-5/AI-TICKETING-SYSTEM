"""
Deletes all marketplace data (vendors, their products, negotiations, and
orders) for a tenant, so `seed_marketplace.py` can be run again to produce a
fresh one-vendor-per-category dataset.

Deliberately a separate file from seed_marketplace.py -- app/main.py's
startup lifespan hook only ever imports seed_marketplace, so this destructive
script can never be reached automatically on a routine app restart.

Deletes rows in FK-safe order: Order.negotiation_session_id references
NegotiationSession, so Order rows must go before NegotiationSession rows.
Demo customers are left untouched -- they aren't category-scoped and there's
no correctness reason to wipe them.

Usage:
    python -m app.scripts.reset_marketplace
"""
from app.db.database import SessionLocal
from app.db.models import (
    NegotiationMessage,
    NegotiationSession,
    Notification,
    Order,
    Product,
    ProductImage,
    User,
    Vendor,
)


def reset_marketplace_demo_data(tenant_id: int = 1) -> dict:
    db = SessionLocal()
    try:
        vendor_user_ids = [
            row[0] for row in db.query(Vendor.user_id).filter(Vendor.tenant_id == tenant_id).all()
        ]
        product_ids = [
            row[0] for row in db.query(Product.id).filter(Product.tenant_id == tenant_id).all()
        ]
        session_ids = [
            row[0] for row in db.query(NegotiationSession.id)
            .filter(NegotiationSession.tenant_id == tenant_id).all()
        ]

        counts = {}
        counts["negotiation_messages"] = (
            db.query(NegotiationMessage)
            .filter(NegotiationMessage.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
        counts["orders"] = (
            db.query(Order).filter(Order.tenant_id == tenant_id).delete(synchronize_session=False)
        )
        counts["negotiation_sessions"] = (
            db.query(NegotiationSession)
            .filter(NegotiationSession.tenant_id == tenant_id)
            .delete(synchronize_session=False)
        )
        counts["product_images"] = (
            db.query(ProductImage)
            .filter(ProductImage.product_id.in_(product_ids))
            .delete(synchronize_session=False)
        )
        counts["products"] = (
            db.query(Product).filter(Product.tenant_id == tenant_id).delete(synchronize_session=False)
        )
        counts["vendors"] = (
            db.query(Vendor).filter(Vendor.tenant_id == tenant_id).delete(synchronize_session=False)
        )
        # Notification.user_id FKs to users.id (NOT NULL) -- clear any
        # notifications addressed to the old vendor logins before deleting
        # those users, or this would violate the FK on Postgres.
        counts["notifications"] = (
            db.query(Notification)
            .filter(Notification.user_id.in_(vendor_user_ids))
            .delete(synchronize_session=False)
        )
        counts["vendor_users"] = (
            db.query(User).filter(User.id.in_(vendor_user_ids)).delete(synchronize_session=False)
        )

        db.commit()
        print(f"Reset marketplace demo data: {counts}")
        return counts
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    confirm = input(
        "This permanently deletes all vendors/products/negotiations/orders "
        "for tenant_id=1. Type 'RESET' to continue: "
    )
    if confirm == "RESET":
        reset_marketplace_demo_data()
    else:
        print("Aborted -- no changes made.")
