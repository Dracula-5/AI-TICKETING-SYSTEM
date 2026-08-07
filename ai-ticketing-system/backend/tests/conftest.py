"""
Shared pytest fixtures for the AI Ticketing System test suite.

Defaults to an in-memory SQLite database so tests are hermetic, fast, and
leave no file-system artefacts. Set TEST_DATABASE_URL to point this suite at
a real database instead (CI's backend-postgres job does this to validate the
full suite against real Postgres) — local `pytest` behavior is unchanged.
The database schema is created fresh for every test session (not per-test)
and individual tests that mutate state use a nested savepoint (subtransaction)
that is rolled back after each test.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.db.models import Product, Tenant, User, Vendor
from app.core.security import get_password_hash, create_access_token
from app.main import app

# ---------------------------------------------------------------------------
# Database wired to the test session (in-memory SQLite by default)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")

connect_args = {"check_same_thread": False} if TEST_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(TEST_DATABASE_URL, connect_args=connect_args)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """Provide a transactional DB session that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """TestClient with the real DB dependency overridden to use the test session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def tenant(db):
    t = Tenant(name="Test Org", domain="testorg.example.com")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def admin_user(db, tenant):
    u = User(
        name="Admin User",
        email="admin@test.com",
        hashed_password=get_password_hash("admin123"),
        role="admin",
        tenant_id=tenant.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def customer_user(db, tenant):
    u = User(
        name="Customer User",
        email="customer@test.com",
        hashed_password=get_password_hash("customer123"),
        role="customer",
        tenant_id=tenant.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def provider_user(db, tenant):
    u = User(
        name="Provider User",
        email="provider@test.com",
        hashed_password=get_password_hash("provider123"),
        role="provider",
        tenant_id=tenant.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def vendor_user(db, tenant):
    u = User(
        name="Vendor User",
        email="vendor@test.com",
        hashed_password=get_password_hash("vendor123"),
        role="vendor",
        tenant_id=tenant.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def vendor(db, tenant, vendor_user):
    v = Vendor(
        user_id=vendor_user.id,
        tenant_id=tenant.id,
        shop_name="Test Shop",
        phone_number="+91-9876543210",
        shop_address="123 Market Street, Test City",
        description="A test vendor shop",
        category="Electronics",
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@pytest.fixture()
def product(db, tenant, vendor):
    p = Product(
        tenant_id=tenant.id,
        vendor_id=vendor.id,
        title="Wireless Headphones",
        description="Noise-cancelling over-ear headphones",
        category="Electronics",
        price=1000.0,
        currency="INR",
        stock_quantity=10,
        status="active",
        floor_price=700.0,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def auth_headers(user: User) -> dict:
    """Return Authorization headers for a given user."""
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}
