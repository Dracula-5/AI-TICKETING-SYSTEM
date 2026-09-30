import csv
import io

import pytest

from app.db.models import Job, Team, Ticket, User
from app.scripts.import_history import HistoryImportError, import_rows
from tests.conftest import make_user

CSV = "\n".join(
    [
        "title,description,created_at,resolved_at,category,priority,team,requester_email",
        "VPN drops,The VPN tunnel drops every hour,2026-01-05T09:00:00Z,2026-01-05T13:00:00Z,"
        "Network & Connectivity,high,Infrastructure,ann@example.com",
        "Laptop fan,Laptop fan is very loud,2026-01-06T10:00:00+00:00,,Hardware,low,Service Desk,",
        "Bad row,,2026-01-06T10:00:00Z,,,,,",
        "Time travel,Resolved before it was opened,2026-01-06T10:00:00Z,2026-01-01T10:00:00Z,,,,",
        "New queue,Needs a new category,2026-01-07T10:00:00Z,2026-01-07T11:00:00Z,Office Moves,medium,Moves Team,",
    ]
)


def rows():
    return csv.DictReader(io.StringIO(CSV))


def test_imports_valid_rows_and_reports_the_rest(db, org_a):
    report = import_rows(db, org_a, rows(), origin="synthetic")
    db.commit()
    assert (report.rows, report.imported) == (5, 2)
    assert len(report.skipped) == 3 and any("--create-missing" in s for s in report.skipped)
    tickets = db.query(Ticket).filter(Ticket.tenant_id == org_a.id).order_by(Ticket.number).all()
    assert [t.status for t in tickets] == ["closed", "submitted"]
    assert all(t.data_origin == "synthetic" and t.channel == "import" for t in tickets)
    assert tickets[0].team.name == "Infrastructure" and tickets[0].resolved_at is not None
    ann = db.query(User).filter(User.email == "ann@example.com").one()
    assert ann.is_active is False and ann.role == "customer" and ann.tenant_id == org_a.id
    assert db.query(Job).filter(Job.kind == "ai.reindex_tenant").count() == 1


def test_create_missing_adds_categories_and_teams(db, org_a):
    report = import_rows(db, org_a, rows(), create_missing=True)
    db.commit()
    assert report.imported == 3 and report.created_categories == ["Office Moves"]
    assert db.query(Team).filter(Team.tenant_id == org_a.id, Team.name == "Moves Team").count() == 1


def test_never_attaches_another_orgs_account(db, org_a, org_b):
    make_user(db, org_b, "customer", "ann@example.com")
    import_rows(db, org_a, rows())
    db.commit()
    t = db.query(Ticket).filter(Ticket.tenant_id == org_a.id, Ticket.title == "VPN drops").one()
    assert t.requester.tenant_id == org_a.id and t.requester.email.endswith(".import.invalid")


def test_rejects_unknown_origin(db, org_a):
    with pytest.raises(HistoryImportError):
        import_rows(db, org_a, rows(), origin="production")
