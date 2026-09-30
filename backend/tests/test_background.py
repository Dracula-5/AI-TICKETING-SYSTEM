"""Worker, email outbox retry/dead-letter, realtime fan-out, storage backends, monitoring."""

import asyncio
import threading
from datetime import timedelta

import pytest

import app.services.email as email_service
import app.services.notification_service as notification_service
from app import worker
from app.core import monitoring
from app.db.database import utcnow
from app.db.models import EmailOutbox, Notification
from app.services.email import MAX_ATTEMPTS, deliver_pending, queue_email
from app.services.notification_ws import NotificationConnectionManager
from app.services.realtime import dispatch
from app.services.storage import S3Storage
from tests.conftest import assign, create_ticket


def _queue(db, n=1):
    for i in range(n):
        queue_email(db, to=f"u{i}@x.example.com", subject="s", body="b", template="t")
    db.commit()


class TestEmailOutbox:
    def test_delivers_queued_messages(self, db):
        _queue(db, 3)
        assert deliver_pending() == 3
        db.expire_all()
        assert {r.status for r in db.query(EmailOutbox)} == {"sent"}
        assert deliver_pending() == 0

    def test_failure_is_retried_with_backoff_then_dead_lettered(self, db, monkeypatch):
        _queue(db)

        def boom(_row):
            raise ConnectionError("smtp down")

        monkeypatch.setattr(email_service, "_send", boom)
        assert deliver_pending() == 0
        db.expire_all()
        row = db.query(EmailOutbox).one()
        assert row.status == "failed" and row.attempts == 1 and "smtp down" in row.last_error
        assert row.next_attempt_at > utcnow()

        # Not due yet -> untouched.
        deliver_pending()
        db.expire_all()
        assert db.query(EmailOutbox).one().attempts == 1

        # Fast-forward through the remaining attempts.
        for _ in range(MAX_ATTEMPTS - 1):
            db.query(EmailOutbox).update({EmailOutbox.next_attempt_at: utcnow() - timedelta(seconds=1)})
            db.commit()
            deliver_pending()
            db.expire_all()
        row = db.query(EmailOutbox).one()
        assert row.status == "dead" and row.attempts == MAX_ATTEMPTS

    def test_backoff_grows_and_caps(self):
        assert email_service._backoff(1) == timedelta(minutes=1)
        assert email_service._backoff(3) == timedelta(minutes=4)
        assert email_service._backoff(20) == timedelta(minutes=60)

    def test_worker_mode_does_not_deliver_inline(self, monkeypatch):
        class Background:
            tasks: list = []

            def add_task(self, fn):
                self.tasks.append(fn)

        bg = Background()
        monkeypatch.setattr(email_service.settings, "background_mode", "worker")
        email_service.schedule_delivery(bg)
        assert bg.tasks == []
        monkeypatch.setattr(email_service.settings, "background_mode", "inline")
        email_service.schedule_delivery(bg)
        assert bg.tasks == [deliver_pending]


class TestWorker:
    def test_jobs_run_on_schedule_and_survive_failures(self, tmp_path, monkeypatch):
        monkeypatch.setattr(worker, "HEARTBEAT_FILE", tmp_path / "hb")
        calls = {"ok": 0, "bad": 0}

        def ok():
            calls["ok"] += 1

        def bad():
            calls["bad"] += 1
            raise RuntimeError("boom")

        stop = threading.Event()
        jobs = [worker.PeriodicJob("ok", 0.01, ok), worker.PeriodicJob("bad", 0.01, bad)]
        t = threading.Thread(target=worker.run, args=(stop, jobs, 0.01))
        t.start()
        try:
            for _ in range(200):
                if calls["ok"] >= 3 and calls["bad"] >= 3:
                    break
                threading.Event().wait(0.01)
        finally:
            stop.set()
            t.join(timeout=5)
        assert calls["ok"] >= 3 and calls["bad"] >= 3  # a failing job doesn't stop the loop
        assert worker.healthy()

    def test_health_check_fails_without_heartbeat(self, tmp_path, monkeypatch):
        monkeypatch.setattr(worker, "HEARTBEAT_FILE", tmp_path / "missing")
        assert not worker.healthy()

    def test_default_jobs(self):
        assert [j.name for j in worker.build_jobs()] == ["sla_sweep", "email_delivery", "jobs", "ai_monitoring"]

    def test_worker_sla_job_uses_its_own_session(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a, priority="critical")["id"]
        assign(client, manager_a, tid, agent_a.id)
        from app.db.models import Ticket

        t = db.get(Ticket, tid)
        t.first_response_due -= timedelta(hours=1)
        db.commit()
        result = worker._sla_sweep()
        assert result["first_response_breaches"] == 1


class TestRealtime:
    def test_published_notifications_bypass_the_local_push(
        self, client, db, manager_a, agent_a, customer_a, monkeypatch
    ):
        published = []
        monkeypatch.setattr(
            notification_service, "publish", lambda uid, payload: published.append((uid, payload)) or True
        )
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        assert [(uid, p["data"]["type"]) for uid, p in published] == [(agent_a.id, "ticket_assigned")]
        assert db.query(Notification).filter(Notification.user_id == agent_a.id).count() == 1

    def test_dispatch_routes_to_the_right_user(self):
        sent = []

        class FakeSocket:
            def __init__(self, name):
                self.name = name

            async def send_json(self, payload):
                sent.append((self.name, payload))

        manager = NotificationConnectionManager()
        asyncio.run(manager.connect(1, FakeSocket("alice")))
        asyncio.run(manager.connect(2, FakeSocket("bob")))
        asyncio.run(dispatch(manager, '{"user_id": 2, "payload": {"type": "notification"}}'))
        assert sent == [("bob", {"type": "notification"})]


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ServerSideEncryption):  # noqa: N803 - boto3 signature
        assert ServerSideEncryption == "AES256"
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        body = self.objects[(Bucket, Key)]

        class Stream:
            def read(self):
                return body

        return {"Body": Stream()}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop((Bucket, Key), None)


class TestS3Storage:
    def test_roundtrip_and_key_validation(self):
        storage = S3Storage("bucket", client=FakeS3())
        key = storage.save(7, b"hello")
        assert key.startswith("t7/")
        assert storage.read(key) == b"hello"
        storage.delete(key)
        assert storage.client.objects == {}
        with pytest.raises(ValueError):
            storage.read("../../etc/passwd")


class TestMonitoring:
    def test_disabled_without_dsn(self):
        assert monitoring.init_error_monitoring("api") is False

    def test_scrubs_credentials_and_bodies(self):
        event = {
            "request": {
                "headers": {"Authorization": "Bearer secret", "Cookie": "nexadesk_refresh=x", "Accept": "*/*"},
                "data": {"password": "hunter2"},
                "cookies": {"nexadesk_refresh": "x"},
            }
        }
        out = monitoring._scrub(event, {})
        assert out["request"]["headers"]["Authorization"] == "[scrubbed]"
        assert out["request"]["headers"]["Cookie"] == "[scrubbed]"
        assert out["request"]["headers"]["Accept"] == "*/*"
        assert "data" not in out["request"] and "cookies" not in out["request"]


def test_db_session_teardown_does_not_use_the_request_threadpool():
    # A sync `yield` dependency closes sessions on the shared request threadpool, which
    # deadlocked the API under load (P10 finding). get_db must stay async.
    import inspect

    from app.db.database import get_db

    assert inspect.isasyncgenfunction(get_db)
