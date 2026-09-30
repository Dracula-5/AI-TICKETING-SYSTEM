"""P12: Prometheus metrics are exposed and reflect real activity."""

from app.services.jobs import run_due_jobs
from tests.conftest import auth, create_ticket


def test_metrics_reflect_requests_jobs_and_backlog(client, db, agent_a, customer_a):
    create_ticket(client, customer_a)
    client.get("/api/v1/tickets", headers=auth(agent_a))
    before = client.get("/metrics").text
    assert 'nexadesk_jobs{status="queued"} 1.0' in before
    run_due_jobs()
    body = client.get("/metrics").text
    # Route templates, not raw paths (bounded label cardinality).
    assert 'nexadesk_http_requests_total{method="POST",route="/api/v1/tickets",status="201"}' in body
    assert "/api/v1/tickets/1" not in body  # never a raw id in a label
    assert 'nexadesk_jobs_total{kind="ai.triage",status="done"}' in body
    assert 'nexadesk_jobs{status="done"} 1.0' in body
    assert "nexadesk_agent_run_duration_seconds_count" in body
    assert "nexadesk_ai_recommendations_awaiting_decision" in body


def test_metrics_are_not_part_of_the_public_api(client):
    assert "/metrics" not in client.get("/api/openapi.json").text


def test_worker_metrics_server_requires_the_token(monkeypatch):
    import socket
    import urllib.error
    import urllib.request

    from app.core import metrics
    from app.core.config import settings

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(settings, "metrics_token", "w" * 32)
    metrics.serve_worker_metrics(port)
    url = f"http://127.0.0.1:{port}/metrics"
    try:
        urllib.request.urlopen(url, timeout=5)  # noqa: S310 -- local test server
        raise AssertionError("expected 401")
    except urllib.error.HTTPError as e:
        assert e.code == 401
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + "w" * 32})
    body = urllib.request.urlopen(req, timeout=5).read().decode()  # noqa: S310
    assert "nexadesk_jobs_total" in body or "python_info" in body


def test_unhandled_errors_are_counted_as_500(client, monkeypatch, agent_a):
    from app.routers import tickets as tickets_router

    def boom(*a, **k):
        raise RuntimeError("database fell over")

    monkeypatch.setattr(tickets_router.svc, "visible_tickets_query", boom)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/api/v1/tickets", headers=auth(agent_a)).status_code == 500
        assert (
            'nexadesk_http_requests_total{method="GET",route="/api/v1/tickets",status="500"}' in c.get("/metrics").text
        )
