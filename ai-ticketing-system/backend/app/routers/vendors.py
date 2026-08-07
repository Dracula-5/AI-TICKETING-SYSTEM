from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import MARKETPLACE_CATEGORIES
from app.db.database import get_db
from app.db.models import User, Vendor
from app.schemas.vendors import (
    VendorRegister,
    VendorUpdate,
    VendorOut,
    VendorPublicOut,
    CategoryAvailabilityOut,
)
from app.schemas.auth import Token
from app.core.limiter import limiter
from app.core.security import (
    get_current_user,
    get_password_hash,
    create_access_token,
    require_role,
)

router = APIRouter(prefix="/vendors", tags=["vendors"])


def _category_taken_error(category: str) -> HTTPException:
    return HTTPException(status_code=400, detail=f"'{category}' already has an assigned vendor")


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def register_vendor(request: Request, payload: VendorRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    taken = db.query(Vendor).filter(
        Vendor.tenant_id == payload.tenant_id, Vendor.category == payload.category,
    ).first()
    if taken:
        raise _category_taken_error(payload.category)

    new_user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role="vendor",
        tenant_id=payload.tenant_id,
    )
    db.add(new_user)
    db.flush()  # assign new_user.id without ending the transaction

    vendor = Vendor(
        user_id=new_user.id,
        tenant_id=payload.tenant_id,
        shop_name=payload.shop_name,
        phone_number=payload.phone_number,
        shop_address=payload.shop_address,
        description=payload.description,
        category=payload.category,
    )
    db.add(vendor)
    try:
        db.commit()
    except IntegrityError:
        # Race: two concurrent registrations for the same tenant+category.
        # The pre-check above closes the common case; this closes the gap.
        db.rollback()
        raise _category_taken_error(payload.category)
    db.refresh(new_user)

    token = create_access_token({"sub": str(new_user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/categories", response_model=list[CategoryAvailabilityOut])
def list_category_availability(tenant_id: int = 1, db: Session = Depends(get_db)):
    """
    Unauthenticated on purpose -- powers the category dropdown on the vendor
    signup page, before the visitor has an account. Must stay registered
    before GET /{vendor_id} or FastAPI's path matching would swallow
    "categories" as a vendor_id and 422 instead of reaching this handler.
    """
    taken_rows = (
        db.query(Vendor.category, Vendor.shop_name)
        .filter(Vendor.tenant_id == tenant_id, Vendor.category.isnot(None))
        .all()
    )
    taken = {category: shop_name for category, shop_name in taken_rows}
    return [
        {"category": c, "available": c not in taken, "shop_name": taken.get(c)}
        for c in MARKETPLACE_CATEGORIES
    ]


def _load_own_vendor(db: Session, current_user: User) -> Vendor:
    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="No vendor profile for this account")
    return vendor


@router.get("/me", response_model=VendorOut)
def get_my_vendor_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    return _load_own_vendor(db, current_user)


@router.put("/me", response_model=VendorOut)
def update_my_vendor_profile(
    payload: VendorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    vendor = _load_own_vendor(db, current_user)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vendor, field, value)

    db.commit()
    db.refresh(vendor)
    return vendor


@router.get("/{vendor_id}", response_model=VendorPublicOut)
def get_vendor_public_profile(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor or vendor.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.get("/", response_model=list[VendorOut])
def list_vendors(
    unverified_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["admin"])

    query = db.query(Vendor).filter(Vendor.tenant_id == current_user.tenant_id)
    if unverified_only:
        query = query.filter(Vendor.is_verified == False)  # noqa: E712
    return query.order_by(Vendor.created_at.desc()).all()


@router.put("/{vendor_id}/verify", response_model=VendorOut)
def verify_vendor(
    vendor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["admin"])

    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor or vendor.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor.is_verified = True
    db.commit()
    db.refresh(vendor)
    return vendor
