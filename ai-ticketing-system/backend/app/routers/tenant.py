from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.db import models
from app.schemas.tenant import TenantCreate, TenantOut

router = APIRouter(
    prefix="/tenants",
    tags=["tenants"]
)

# -------------------------
# CREATE TENANT (POST)
# -------------------------
@router.post("/", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant: TenantCreate,
    db: Session = Depends(get_db)
):
    new_tenant = models.Tenant(
        name=tenant.name,
        domain=tenant.domain
    )

    try:
        db.add(new_tenant)
        db.commit()
        db.refresh(new_tenant)
        return new_tenant

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant with this name or domain already exists"
        )

# -------------------------
# GET TENANT BY ID
# -------------------------
@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db)
):
    tenant = db.query(models.Tenant).filter(
        models.Tenant.id == tenant_id
    ).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return tenant
