from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Provider, User, Tenant
from app.schemas.providers import ProviderCreate, ProviderOut
from app.core.security import get_current_user, require_role

router = APIRouter(prefix="/providers", tags=["providers"])

@router.post("/", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(
    provider: ProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_role(current_user, ["admin"])

    tenant = db.query(Tenant).filter(
        Tenant.id == current_user.tenant_id
    ).first()

    if not tenant:
        raise HTTPException(404, "Tenant not found")

    new_provider = Provider(
        name=provider.name,
        department=provider.department,
        contact=provider.contact,
        tenant_id=current_user.tenant_id
    )

    db.add(new_provider)
    db.commit()
    db.refresh(new_provider)
    return new_provider


@router.get("/", response_model=list[ProviderOut])
def get_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_role(current_user, ["admin", "provider"])
    
    return db.query(Provider).filter(
        Provider.tenant_id == current_user.tenant_id
    ).all()
