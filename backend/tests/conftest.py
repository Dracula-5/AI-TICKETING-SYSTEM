"""
Test fixtures.

The app is configured for tests *before* it is imported: in-memory SQLite
shared through a StaticPool (or TEST_DATABASE_URL, e.g. Postgres in CI), a
low bcrypt cost, no background SLA loop, and an unreachable Redis so the
cache's fail-open path is what runs. The schema is created once per session
and every table is emptied after each test, so tests are isolated without the
per-test app start-up cost the previous suite paid.
"""

import os
import tempfile

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789abcdef"
os.environ["SLA_SWEEP_ENABLED"] = "false"
os.environ["JOB_RUNNER_ENABLED"] = "false"  # tests run jobs explicitly (run_due_jobs)
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
os.environ["ATTACHMENT_DIR"] = tempfile.mkdtemp(prefix="nexadesk-test-attachments-")
# Deterministic offline embedder: no model downloads in tests (never used for metrics).
os.environ["EMBEDDING_MODEL"] = "test-hashing"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.limiter import limiter  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.models import Team, TeamMember, Tenant, User  # noqa: E402
from app.main import app  # noqa: E402
from app.services.organizations import create_organization  # noqa: E402

PASSWORD = "Correct-Horse-9"


def _migration_module(name: str):
    """Load a migration file (for its PostgreSQL-only DDL) without Alembic's runner."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"migration_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session", autouse=True)
def _schema():
    if engine.dialect.name == "postgresql":  # migrations do this in real deployments (0003)
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":  # PostgreSQL-only objects from migration 0005
        with engine.begin() as conn:
            for statement in _migration_module("0005_knowledge_base").PG_UP:
                conn.execute(text(statement))
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(autouse=True)
def _rate_limits_off():
    limiter.reset()
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------
def make_org(db, name="Acme Corp", **kwargs) -> Tenant:
    tenant = create_organization(db, name, **kwargs)
    db.commit()
    return tenant


def make_user(db, tenant: Tenant | None, role: str, email: str, name: str | None = None, teams=(), **kwargs) -> User:
    user = User(
        name=name or email.split("@")[0].replace(".", " ").title(),
        email=email,
        hashed_password=get_password_hash(PASSWORD),
        role=role,
        tenant_id=tenant.id if tenant else None,
        **kwargs,
    )
    db.add(user)
    db.flush()
    for team_name in teams:
        team = db.query(Team).filter(Team.tenant_id == tenant.id, Team.name == team_name).one()
        db.add(TeamMember(team_id=team.id, user_id=user.id))
    db.commit()
    return user


def auth(user: User) -> dict:
    token, _ = create_access_token(user.id, user.tenant_id, user.role)
    return {"Authorization": f"Bearer {token}"}


def team_id(db, tenant: Tenant, name: str) -> int:
    return db.query(Team.id).filter(Team.tenant_id == tenant.id, Team.name == name).scalar()


# ---------------------------------------------------------------------------
# A standard two-organization world
# ---------------------------------------------------------------------------
@pytest.fixture()
def org_a(db):
    return make_org(db, "Acme Corp")


@pytest.fixture()
def org_b(db):
    return make_org(db, "Globex")


@pytest.fixture()
def admin_a(db, org_a):
    return make_user(db, org_a, "org_admin", "admin@acme.example.com")


@pytest.fixture()
def manager_a(db, org_a):
    return make_user(db, org_a, "manager", "manager@acme.example.com")


@pytest.fixture()
def agent_a(db, org_a):
    return make_user(db, org_a, "agent", "agent@acme.example.com", teams=["Service Desk", "Infrastructure"])


@pytest.fixture()
def agent_a2(db, org_a):
    return make_user(db, org_a, "agent", "agent2@acme.example.com", teams=["Service Desk"])


@pytest.fixture()
def customer_a(db, org_a):
    return make_user(db, org_a, "customer", "alice@acme.example.com")


@pytest.fixture()
def customer_a2(db, org_a):
    return make_user(db, org_a, "customer", "bob@acme.example.com")


@pytest.fixture()
def analyst_a(db, org_a):
    return make_user(db, org_a, "analyst", "analyst@acme.example.com")


@pytest.fixture()
def admin_b(db, org_b):
    return make_user(db, org_b, "org_admin", "admin@globex.example.com")


@pytest.fixture()
def agent_b(db, org_b):
    return make_user(db, org_b, "agent", "agent@globex.example.com", teams=["Service Desk"])


@pytest.fixture()
def customer_b(db, org_b):
    return make_user(db, org_b, "customer", "carol@globex.example.com")


@pytest.fixture()
def platform_admin(db):
    return make_user(db, None, "platform_admin", "ops@nexadesk.example.com")


def create_ticket(
    client, user, title="VPN keeps disconnecting", description="The VPN drops every 10 minutes.", **extra
):
    resp = client.post(
        "/api/v1/tickets", json={"title": title, "description": description, **extra}, headers=auth(user)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def move(client, user, ticket_id, to_status, **extra):
    return client.post(
        f"/api/v1/tickets/{ticket_id}/transitions", json={"to_status": to_status, **extra}, headers=auth(user)
    )


def assign(client, user, ticket_id, assignee_id, **extra):
    return client.post(
        f"/api/v1/tickets/{ticket_id}/assign", json={"assignee_id": assignee_id, **extra}, headers=auth(user)
    )


@pytest.fixture()
def manager_b(db, org_b):
    return make_user(db, org_b, "manager", "mia@globex.example.com")
