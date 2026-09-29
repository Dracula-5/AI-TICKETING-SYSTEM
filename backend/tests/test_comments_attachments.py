import pytest

from app.db.models import Notification, Ticket
from app.services.storage import UploadRejected, sanitize_filename, validate_upload
from tests.conftest import assign, auth, create_ticket

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n..."


def upload(client, user, tid, name, content, **extra):
    return client.post(
        f"{API}/tickets/{tid}/attachments",
        files={"file": (name, content, "application/octet-stream")},
        headers=auth(user),
        **extra,
    )


class TestComments:
    def test_staff_public_reply_counts_as_first_response(self, client, db, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        client.post(
            f"{API}/tickets/{tid}/comments",
            json={"content": "Internal only", "visibility": "internal"},
            headers=auth(agent_a),
        )
        assert db.get(Ticket, tid).first_responded_at is None
        client.post(f"{API}/tickets/{tid}/comments", json={"content": "Looking into it"}, headers=auth(agent_a))
        db.expire_all()
        assert db.get(Ticket, tid).first_responded_at is not None

    def test_reply_notifies_the_other_party(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        client.post(f"{API}/tickets/{tid}/comments", json={"content": "Can you restart?"}, headers=auth(agent_a))
        client.post(f"{API}/tickets/{tid}/comments", json={"content": "Done"}, headers=auth(customer_a))
        kinds = {(n.user_id, n.type) for n in db.query(Notification).all()}
        assert (customer_a.id, "ticket_comment") in kinds and (agent_a.id, "ticket_comment") in kinds

    def test_mentions_notify_staff_but_internal_notes_never_reach_customers(
        self, client, db, manager_a, agent_a, customer_a
    ):
        tid = create_ticket(client, customer_a)["id"]
        client.post(
            f"{API}/tickets/{tid}/comments",
            json={"content": f"@{manager_a.email} @{customer_a.email} thoughts?", "visibility": "internal"},
            headers=auth(agent_a),
        )
        mentioned = {n.user_id for n in db.query(Notification).filter(Notification.type == "mention")}
        assert mentioned == {manager_a.id}

    def test_author_is_recorded(self, client, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        c = client.post(f"{API}/tickets/{tid}/comments", json={"content": "hi"}, headers=auth(agent_a)).json()
        assert c["author"]["id"] == agent_a.id and c["visibility"] == "public"


class TestUploadValidation:
    @pytest.mark.parametrize(
        "name,data",
        [
            ("shot.png", PNG),
            ("doc.pdf", PDF),
            ("notes.txt", "héllo".encode()),
            ("data.csv", b"a,b\n1,2"),
        ],
    )
    def test_accepts_allowed_types(self, name, data):
        assert validate_upload(name, data)[0] == name

    @pytest.mark.parametrize(
        "name,data,why",
        [
            ("evil.exe", b"MZ\x90\x00", "not allowed"),
            ("page.html", b"<script>alert(1)</script>", "not allowed"),
            ("image.svg", b"<svg onload=alert(1)>", "not allowed"),
            ("fake.png", b"<html>not a png</html>", "does not match"),
            ("fake.pdf", PNG, "does not match"),
            ("binary.txt", b"\xff\xfe\x00\x01", "UTF-8"),
            ("empty.txt", b"", "empty"),
            ("noext", b"hello", "not allowed"),
        ],
    )
    def test_rejects(self, name, data, why):
        with pytest.raises(UploadRejected, match=why):
            validate_upload(name, data)

    def test_filename_is_sanitized(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"
        assert sanitize_filename("C:\\temp\\a<b>.txt") == "a_b_.txt"
        assert sanitize_filename("") == "file"


class TestAttachmentsApi:
    def test_upload_and_download_roundtrip(self, client, customer_a, agent_a):
        tid = create_ticket(client, customer_a)["id"]
        r = upload(client, customer_a, tid, "screenshot.png", PNG)
        assert r.status_code == 201
        att = r.json()
        assert att["content_type"] == "image/png" and att["size_bytes"] == len(PNG)
        dl = client.get(f"{API}/attachments/{att['id']}/download", headers=auth(agent_a))
        assert dl.status_code == 200 and dl.content == PNG
        assert dl.headers["content-disposition"] == 'attachment; filename="screenshot.png"'
        assert dl.headers["x-content-type-options"] == "nosniff"

    def test_rejected_upload_returns_422(self, client, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assert upload(client, customer_a, tid, "run.exe", b"MZ").status_code == 422

    def test_oversize_rejected(self, client, customer_a, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "attachment_max_bytes", 10)
        tid = create_ticket(client, customer_a)["id"]
        assert upload(client, customer_a, tid, "big.txt", b"x" * 11).status_code == 422

    def test_cannot_attach_to_someone_elses_comment(self, client, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        c = client.post(f"{API}/tickets/{tid}/comments", json={"content": "x"}, headers=auth(agent_a)).json()
        r = upload(client, customer_a, tid, "a.txt", b"hi", data={"comment_id": c["id"]})
        assert r.status_code == 404
