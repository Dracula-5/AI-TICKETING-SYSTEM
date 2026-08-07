import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Product, ProductImage, User, Vendor
from app.schemas.products import ProductCreate, ProductUpdate, ProductOut, ProductListOut
from app.core.security import get_current_user, require_role
from app.core.cache import cache_get, cache_set

router = APIRouter(prefix="/products", tags=["products"])

ALLOWED_STATUS = ["active", "inactive", "out_of_stock"]
ALLOWED_SORT = ["newest", "price_asc", "price_desc", "popular"]
PRODUCT_LIST_CACHE_TTL = 20


def _product_list_cache_key(tenant_id: int, **params) -> str:
    raw = f"{tenant_id}:" + ":".join(f"{k}={v}" for k, v in sorted(params.items()))
    return "products:list:" + hashlib.sha256(raw.encode()).hexdigest()


def _load_own_vendor(db: Session, current_user: User) -> Vendor:
    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="No vendor profile for this account")
    return vendor


def _load_product_for_tenant(product_id: int, db: Session, current_user: User) -> Product:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or product.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ========================
# Marketplace listing (public browsing, tenant-scoped)
# ========================
@router.get("/", response_model=ProductListOut)
def list_products(
    search: str | None = None,
    category: str | None = None,
    vendor_id: int | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    sort: str = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if sort not in ALLOWED_SORT:
        raise HTTPException(status_code=400, detail=f"sort must be one of {ALLOWED_SORT}")

    cache_key = _product_list_cache_key(
        current_user.tenant_id,
        search=search, category=category, vendor_id=vendor_id,
        min_price=min_price, max_price=max_price, sort=sort,
        page=page, page_size=page_size,
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    query = db.query(Product).filter(
        Product.tenant_id == current_user.tenant_id,
        Product.status == "active",
    )

    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.title.ilike(like), Product.description.ilike(like)))
    if category:
        query = query.filter(Product.category == category)
    if vendor_id:
        query = query.filter(Product.vendor_id == vendor_id)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort == "popular":
        query = query.order_by(Product.views_count.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    result = {"items": items, "total": total, "page": page, "page_size": page_size}
    serialized = ProductListOut.model_validate(result).model_dump(mode="json")
    cache_set(cache_key, serialized, PRODUCT_LIST_CACHE_TTL)
    return serialized


@router.get("/admin/all", response_model=ProductListOut)
def list_all_products_admin(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Every product for the tenant regardless of status, for moderation.
    Not cached -- moderators need current data, not a briefly-stale view.
    """
    require_role(current_user, ["admin"])

    query = db.query(Product).filter(Product.tenant_id == current_user.tenant_id)
    if status_filter:
        if status_filter not in ALLOWED_STATUS:
            raise HTTPException(status_code=400, detail=f"status must be one of {ALLOWED_STATUS}")
        query = query.filter(Product.status == status_filter)
    query = query.order_by(Product.created_at.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/vendor/my-products", response_model=list[ProductOut])
def list_my_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    vendor = _load_own_vendor(db, current_user)
    return (
        db.query(Product)
        .filter(Product.vendor_id == vendor.id)
        .order_by(Product.created_at.desc())
        .all()
    )


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = _load_product_for_tenant(product_id, db, current_user)
    product.views_count = (product.views_count or 0) + 1
    db.commit()
    db.refresh(product)
    return product


# ========================
# Vendor product management
# ========================
@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    vendor = _load_own_vendor(db, current_user)

    product = Product(
        tenant_id=current_user.tenant_id,
        vendor_id=vendor.id,
        title=payload.title,
        description=payload.description,
        category=vendor.category,
        price=payload.price,
        currency=payload.currency,
        stock_quantity=payload.stock_quantity,
        floor_price=payload.floor_price,
        auto_negotiate_enabled=payload.auto_negotiate_enabled,
    )
    db.add(product)
    db.flush()

    for idx, url in enumerate(payload.image_urls):
        db.add(ProductImage(product_id=product.id, url=url, sort_order=idx))

    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["vendor"])
    vendor = _load_own_vendor(db, current_user)
    product = _load_product_for_tenant(product_id, db, current_user)

    if product.vendor_id != vendor.id:
        raise HTTPException(status_code=403, detail="You do not own this product")

    updates = payload.model_dump(exclude_unset=True, exclude={"image_urls"})
    for field, value in updates.items():
        setattr(product, field, value)

    if payload.image_urls is not None:
        db.query(ProductImage).filter(ProductImage.product_id == product.id).delete()
        for idx, url in enumerate(payload.image_urls):
            db.add(ProductImage(product_id=product.id, url=url, sort_order=idx))

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = _load_product_for_tenant(product_id, db, current_user)

    if current_user.role != "admin":
        require_role(current_user, ["vendor"])
        vendor = _load_own_vendor(db, current_user)
        if product.vendor_id != vendor.id:
            raise HTTPException(status_code=403, detail="You do not own this product")

    db.delete(product)
    db.commit()
    return None


# ========================
# Admin moderation
# ========================
@router.put("/{product_id}/status", response_model=ProductOut)
def set_product_status(
    product_id: int,
    new_status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_role(current_user, ["admin"])

    if new_status not in ALLOWED_STATUS:
        raise HTTPException(status_code=400, detail=f"status must be one of {ALLOWED_STATUS}")

    product = _load_product_for_tenant(product_id, db, current_user)
    product.status = new_status
    db.commit()
    db.refresh(product)
    return product
