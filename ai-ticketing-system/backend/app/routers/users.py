from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ProviderCategory, User, Tenant
from app.schemas.users import UserCreate, UserOut, UserUpdate, PasswordChange
from app.schemas.notifications import ProviderCategoriesIn, ProviderCategoriesOut
from app.core.security import get_password_hash, get_current_user, verify_password
from app.services.seed_users import create_default_users

router = APIRouter(prefix="/users", tags=["users"])

PROVIDER_ROLES = ["provider", "service_provider"]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        name=user.name,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role=user.role,
        tenant_id=user.tenant_id
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@router.get("/", response_model=list[UserOut])
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(User).filter(
        User.tenant_id == current_user.tenant_id
    ).all()

@router.get("/providers", response_model=list[UserOut])
def get_provider_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    return db.query(User).filter(
        User.tenant_id == current_user.tenant_id,
        User.role.in_(["provider", "service_provider"])
    ).all()

@router.put("/me", response_model=UserOut)
def update_my_profile(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.email and payload.email != current_user.email:
        existing = db.query(User).filter(
            User.email == payload.email, User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/me/password")
def change_my_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Password updated"}


@router.get("/me/categories", response_model=ProviderCategoriesOut)
def get_my_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in PROVIDER_ROLES:
        raise HTTPException(status_code=403, detail="Only providers have category preferences")

    rows = db.query(ProviderCategory).filter(ProviderCategory.user_id == current_user.id).all()
    return {"categories": [r.category for r in rows]}


@router.put("/me/categories", response_model=ProviderCategoriesOut)
def set_my_categories(
    payload: ProviderCategoriesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in PROVIDER_ROLES:
        raise HTTPException(status_code=403, detail="Only providers have category preferences")

    db.query(ProviderCategory).filter(ProviderCategory.user_id == current_user.id).delete()
    deduped = sorted(set(payload.categories))
    for category in deduped:
        db.add(ProviderCategory(user_id=current_user.id, category=category))
    db.commit()

    return {"categories": deduped}


@router.post("/create-default-users")
def seed_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        return {"error": "Only admin can run this"}

    created = create_default_users(db)

    return {
        "message": "Default users ready",
        "created_count": created
    }


