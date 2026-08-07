from sqlalchemy.orm import Session
from app.db.models import User, Tenant
from app.core.security import get_password_hash

def create_default_tenant(db: Session) -> int:
    tenant = db.query(Tenant).filter(Tenant.id == 1).first()
    if tenant:
        return tenant.id

    tenant = Tenant(
        name="Default Tenant",
        domain="default.local"
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant.id


def create_default_users(db: Session):
    tenant_id = create_default_tenant(db)
    default_users = [
        {
            "name": "Admin",
            "email": "admin@gmail.com",
            "password": "admin123",
            "role": "admin",
            "tenant_id": tenant_id
        },
        {
            "name": "Provider",
            "email": "provider@gmail.com",
            "password": "provider123",
            "role": "provider",
            "tenant_id": tenant_id
        },
        {
            "name": "Customer",
            "email": "customer@gmail.com",
            "password": "customer123",
            "role": "customer",
            "tenant_id": tenant_id
        },
    ]

    created = 0

    for u in default_users:
        exists = db.query(User).filter(User.email == u["email"]).first()
        if not exists:
            user = User(
                name=u["name"],
                email=u["email"],
                hashed_password=get_password_hash(u["password"]),
                role=u["role"],
                tenant_id=u["tenant_id"]
            )
            db.add(user)
            created += 1

    db.commit()
    return created
