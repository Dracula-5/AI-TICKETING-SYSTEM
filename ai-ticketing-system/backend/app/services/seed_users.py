from sqlalchemy.orm import Session
from app.db.models import User
from app.core.security import get_password_hash


def create_default_users(db: Session):
    default_users = [
        {
            "name": "Admin",
            "email": "admin@gmail.com",
            "password": "admin123",
            "role": "admin",
            "tenant_id": 1
        },
        {
            "name": "Provider",
            "email": "provider@gmail.com",
            "password": "provider123",
            "role": "provider",
            "tenant_id": 1
        },
        {
            "name": "Customer",
            "email": "customer@gmail.com",
            "password": "customer123",
            "role": "customer",
            "tenant_id": 1
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
