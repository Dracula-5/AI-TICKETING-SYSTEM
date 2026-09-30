"""
P14 — tests mapped to the threat model in docs/security.md (T-ids).
Each test asserts the control, not just the happy path.
"""

import io
import time

import jwt
import pytest

from app.core.config import settings
from app.db.models import Ticket
from app.services.jobs import run_due_jobs
from tests.conftest import auth, create_ticket

API = "/api/v1"


class TestT1Injection:
    @pytest.mark.parametrize("q", ["' OR '1'='1", "1; DROP TABLE tickets; --", "%' --", "\\", "_%_", "#1 OR 1=1"])
    def test_search_parameters_are_data(self, client, db, customer_a, agent_a, customer_b, q):
        create_ticket(client, customer_b, title="Org B secret")
        mine = create_ticket(client, customer_a, title="Printer offline")
        r = client.get(f"{API}/tickets", params={"q": q}, headers=auth(agent_a))
        assert r.status_code == 200
        assert all(t["id"] == mine["id"] for t in r.json()["items"])  # never another tenant's rows
        assert db.query(Ticket).count() == 2  # nothing dropped

    @pytest.mark.parametrize("q", ["') OR 1=1 --", "!!&&||", "vpn:* & !x"])
    def test_kb_search_query_syntax_cannot_break_out(self, client, agent_a, q):
        assert client.get(f"{API}/kb/search", params={"q": q}, headers=auth(agent_a)).status_code == 200


class TestT2StoredXss:
    def test_markup_is_stored_and_returned_as_inert_json(self, client, agent_a, customer_a):
        payload = '<img src=x onerror=alert(1)><script>alert("x")</script>'
        t = create_ticket(client, customer_a, title=payload[:120], description=payload)
        r = client.get(f"{API}/tickets/{t['id']}", headers=auth(agent_a))
        assert r.headers["content-type"].startswith("application/json")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'none'" in r.headers["content-security-policy"]
        assert r.json()["description"] == payload  # stored verbatim; the SPA renders it as text


class TestT3Uploads:
    def upload(self, client, user, ticket_id, name, data):
        return client.post(
            f"{API}/tickets/{ticket_id}/attachments",
            headers=auth(user),
            files={"file": (name, io.BytesIO(data), "application/octet-stream")},
        )

    @pytest.mark.parametrize(
        "name,data",
        [
            ("evil.svg", b"<svg onload=alert(1)>"),
            ("evil.html", b"<script>alert(1)</script>"),
            ("run.exe", b"MZ\x90\x00"),
            ("fake.pdf", b"<html><script>alert(1)</script>"),  # extension/content mismatch
            ("image.png", b"GIF89a....."),
        ],
    )
    def test_dangerous_or_mismatched_files_are_rejected(self, client, customer_a, name, data):
        t = create_ticket(client, customer_a)
        assert self.upload(client, customer_a, t["id"], name, data).status_code == 422

    def test_text_that_looks_like_html_is_served_as_a_download(self, client, customer_a, agent_a):
        t = create_ticket(client, customer_a)
        att = self.upload(client, customer_a, t["id"], "../../notes.txt", b"<script>alert(1)</script>").json()
        assert "/" not in att["filename"] and ".." not in att["filename"]
        r = client.get(f"{API}/attachments/{att['id']}/download", headers=auth(agent_a))
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["content-type"].startswith("text/plain")
        assert r.headers["x-content-type-options"] == "nosniff"


class TestT4TenantIsolation:
    def test_org_b_cannot_reach_org_a_objects_through_ai_and_kb_endpoints(
        self, client, db, manager_a, customer_a, admin_b, agent_b
    ):
        t = create_ticket(client, customer_a, title="VPN tunnel drops", description="VPN drops on wifi")
        client.post(
            f"{API}/kb/documents",
            headers=auth(manager_a),
            data={"visibility": "internal"},
            files={"file": ("vpn.md", io.BytesIO(b"# VPN\n\nReset the VPN tunnel."), "text/markdown")},
        )
        run_due_jobs()
        tid = t["id"]
        doc_id = client.get(f"{API}/kb/documents", headers=auth(manager_a)).json()[0]["id"]
        for user in (admin_b, agent_b):
            h = auth(user)
            assert client.get(f"{API}/tickets/{tid}", headers=h).status_code == 404
            assert client.get(f"{API}/tickets/{tid}/ai", headers=h).status_code in (403, 404)
            assert client.get(f"{API}/tickets/{tid}/agent/runs", headers=h).status_code in (403, 404)
            assert client.get(f"{API}/tickets/{tid}/ai/knowledge", headers=h).status_code in (403, 404)
            assert client.post(f"{API}/tickets/{tid}/ai/analyze", headers=h).status_code in (403, 404, 503)
            assert client.get(f"{API}/kb/documents/{doc_id}", headers=h).status_code == 404
            assert client.get(f"{API}/kb/search", params={"q": "VPN tunnel"}, headers=h).json()["hits"] == []
            assert client.get(f"{API}/ai/queue", headers=h).json()["total"] == 0


class TestT6MassAssignment:
    def test_protected_fields_cannot_be_set_through_updates(self, client, db, customer_a, manager_a, org_b):
        t = create_ticket(client, customer_a)
        r = client.patch(
            f"{API}/tickets/{t['id']}",
            headers=auth(manager_a),
            json={"tenant_id": org_b.id, "status": "closed", "number": 999, "data_origin": "real"},
        )
        db.expire_all()
        ticket = db.get(Ticket, t["id"])
        assert ticket.tenant_id != org_b.id and ticket.status != "closed" and ticket.number != 999
        assert r.status_code in (200, 422)


class TestT7Tokens:
    def claims(self, user, **over):
        now = int(time.time())
        return {
            "sub": str(user.id),
            "tid": user.tenant_id,
            "role": user.role,
            "type": "access",
            "iat": now,
            "exp": now + 300,
            **over,
        }

    def test_forged_expired_and_unsigned_tokens_are_refused(self, client, agent_a):
        forged = jwt.encode(self.claims(agent_a, role="org_admin"), "not-the-server-key", algorithm="HS256")
        expired = jwt.encode(self.claims(agent_a, exp=int(time.time()) - 10), settings.secret_key, algorithm="HS256")
        unsigned = jwt.encode(self.claims(agent_a), key=None, algorithm="none")
        refresh_as_access = jwt.encode(self.claims(agent_a, type="refresh"), settings.secret_key, algorithm="HS256")
        for token in (forged, expired, unsigned, refresh_as_access, "garbage"):
            r = client.get(f"{API}/tickets", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401, token[:20]

    def test_role_claim_is_not_trusted(self, client, agent_a):
        # A validly signed token claiming a higher role still acts with the stored role.
        token = jwt.encode(self.claims(agent_a, role="org_admin"), settings.secret_key, algorithm="HS256")
        r = client.patch(
            f"{API}/organizations/me", headers={"Authorization": f"Bearer {token}"}, json={"name": "Pwned"}
        )
        assert r.status_code == 403
