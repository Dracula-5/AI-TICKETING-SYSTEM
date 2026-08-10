"""
Populates the default tenant with exactly one vendor per marketplace
category (see app/core/constants.py's MARKETPLACE_CATEGORIES), each fully
stocked with products in their own category, plus demo customers.

Usage:
    python -m app.scripts.seed_marketplace

Idempotent: skips vendor/product seeding (and exits cleanly) if any vendor
already exists for the default tenant, so it's safe to run more than once.
To replace existing demo vendors/products with a fresh set, run
`python -m app.scripts.reset_marketplace` first.

Not run automatically on app startup except when SEED_MARKETPLACE_DEMO_DATA
is enabled (see app/main.py lifespan / docker-compose.yml) — production
databases should never get fake data by default.
"""
import random

from faker import Faker

from app.db.database import SessionLocal
from app.db.models import Product, ProductImage, User, Vendor
from app.core.security import get_password_hash
from app.services.seed_users import create_default_tenant

fake = Faker()

CUSTOMER_COUNT = 40

# One deterministic shop per category so manual testing/demoing always knows
# exactly which login owns which category (e.g. electronics@vendor-demo.com
# / vendor123 is always "the Electronics vendor").
CATEGORY_BLUEPRINT = [
    {
        "category": "Electronics",
        "shop_name": "Volt & Byte Electronics",
        "owner_name": "Aditya Rao",
        "email": "electronics@vendor-demo.com",
        "items": ["Headphones", "Bluetooth Speaker", "Smartwatch", "Power Bank", "Webcam", "Router"],
    },
    {
        "category": "Home & Kitchen",
        "shop_name": "Hearth & Home Essentials",
        "owner_name": "Priya Nair",
        "email": "homekitchen@vendor-demo.com",
        "items": ["Non-stick Pan", "Blender", "Table Lamp", "Storage Rack", "Pressure Cooker", "Bedsheet Set"],
    },
    {
        "category": "Fashion",
        "shop_name": "Threadline Fashion Co.",
        "owner_name": "Karan Mehta",
        "email": "fashion@vendor-demo.com",
        "items": ["Cotton T-Shirt", "Running Shoes", "Leather Wallet", "Denim Jacket", "Sunglasses", "Backpack"],
    },
    {
        "category": "Grocery",
        "shop_name": "GreenCart Grocery",
        "owner_name": "Sunita Iyer",
        "email": "grocery@vendor-demo.com",
        "items": ["Basmati Rice 5kg", "Organic Honey", "Green Tea Pack", "Cold-pressed Oil", "Almonds 500g"],
    },
    {
        "category": "Books",
        "shop_name": "Chapter & Verse Books",
        "owner_name": "Rohan Das",
        "email": "books@vendor-demo.com",
        "items": ["Fiction Novel", "Self-Help Guide", "Cookbook", "Children's Storybook", "Programming Handbook"],
    },
    {
        "category": "Sports",
        "shop_name": "Peak Performance Sports",
        "owner_name": "Ananya Singh",
        "email": "sports@vendor-demo.com",
        "items": ["Yoga Mat", "Cricket Bat", "Football", "Dumbbell Set", "Cycling Helmet"],
    },
]


def _unique_email(db, base: str) -> str:
    email = base
    suffix = 1
    while db.query(User).filter(User.email == email).first():
        suffix += 1
        email = base.replace("@", f"{suffix}@")
    return email


def seed_marketplace() -> dict:
    db = SessionLocal()
    try:
        already_seeded = db.query(Vendor).first() is not None
        if already_seeded:
            print("Marketplace already has vendors - skipping seed (run reset_marketplace first to replace).")
            return {"vendors": 0, "products": 0, "customers": 0}

        tenant_id = create_default_tenant(db)

        vendors_created = 0
        products_created = 0
        customers_created = 0

        for blueprint in CATEGORY_BLUEPRINT:
            email = _unique_email(db, blueprint["email"])
            user = User(
                name=blueprint["owner_name"],
                email=email,
                hashed_password=get_password_hash("vendor123"),
                role="vendor",
                tenant_id=tenant_id,
            )
            db.add(user)
            db.flush()

            vendor = Vendor(
                user_id=user.id,
                tenant_id=tenant_id,
                shop_name=blueprint["shop_name"],
                phone_number=fake.phone_number(),
                shop_address=fake.address().replace("\n", ", "),
                description=fake.catch_phrase(),
                category=blueprint["category"],
                is_verified=True,  # each is their category's sole vendor
                rating_avg=round(random.uniform(4.0, 5.0), 1),
            )
            db.add(vendor)
            db.flush()
            vendors_created += 1

            for item_name in blueprint["items"]:
                title = f"{fake.word().capitalize()} {item_name}"
                price = round(random.uniform(199, 24999), 2)

                product = Product(
                    tenant_id=tenant_id,
                    vendor_id=vendor.id,
                    title=title,
                    description=fake.paragraph(nb_sentences=3),
                    category=blueprint["category"],
                    price=price,
                    currency="INR",
                    stock_quantity=random.randint(5, 150),  # never 0 -- always buyable/negotiable
                    status="active",
                    views_count=random.randint(0, 500),
                )
                db.add(product)
                db.flush()

                seed = f"{vendor.id}-{product.id}"
                db.add(ProductImage(product_id=product.id, url=f"https://picsum.photos/seed/{seed}/640/480", sort_order=0))
                products_created += 1

        existing_customers = db.query(User).filter(
            User.role == "customer", User.tenant_id == tenant_id
        ).count()
        for _ in range(max(0, CUSTOMER_COUNT - existing_customers)):
            name = fake.name()
            email = _unique_email(db, f"{name.lower().replace(' ', '.')}@customer-demo.com")
            db.add(User(
                name=name,
                email=email,
                hashed_password=get_password_hash("customer123"),
                role="customer",
                tenant_id=tenant_id,
            ))
            customers_created += 1

        db.commit()
        summary = {
            "vendors": vendors_created,
            "products": products_created,
            "customers": customers_created,
        }
        print(f"Seeded marketplace demo data: {summary}")
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    seed_marketplace()
