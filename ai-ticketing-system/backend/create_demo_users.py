from app.db.database import SessionLocal
from app.db.models import User, Tenant
from app.core.security import get_password_hash

db = SessionLocal()

# Create Tenant
tenant = Tenant(name="DemoTenant", domain="demo.com")
db.add(tenant)
db.commit()
db.refresh(tenant)

users = [
    {
        "name": "Admin",
        "email": "admin@test.com",
        "password": "admin123",
        "role": "admin"
    },
    {
        "name": "Customer",
        "email": "customer@test.com",
        "password": "customer123",
        "role": "customer"
    },
    {
        "name": "Provider",
        "email": "provider@test.com",
        "password": "provider123",
        "role": "provider"
    }
]

for u in users:
    user = User(
        name=u["name"],
        email=u["email"],
        hashed_password=get_password_hash(u["password"]),
        role=u["role"],
        tenant_id=tenant.id
    )
    db.add(user)

db.commit()

print("✅ DEMO USERS CREATED")
