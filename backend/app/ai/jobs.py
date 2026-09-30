"""Background job handlers for AI work (registered on import)."""

from sqlalchemy.orm import Session

from app.db.models import Ticket
from app.services.jobs import handler


@handler("ai.triage")
def triage_ticket(db: Session, payload: dict) -> dict:
    ticket = db.get(Ticket, payload["ticket_id"])
    if ticket is None:
        return {"skipped": "ticket no longer exists"}
    from app.agent import runner

    agent_run = runner.run(db, ticket, trigger="ticket_created")
    if agent_run is None:
        return {"skipped": "AI disabled"}
    return {"agent_run": agent_run.id, "steps": {s["kind"]: s.get("outcome") for s in agent_run.steps}}


@handler("ai.reindex_tenant")
def reindex_tenant(db: Session, payload: dict) -> dict:
    """Embed every ticket of an organization (e.g. after changing the model or
    importing history). Recommendations are only issued for tickets still open,
    and only when asked (`triage_open`) — never retroactively for closed work."""
    from app.ai import index
    from app.ai.embedder import get_embedder, ticket_text

    embedder = get_embedder()
    if embedder is None:
        return {"skipped": "AI disabled"}
    rows = db.query(Ticket).filter(Ticket.tenant_id == payload["tenant_id"]).order_by(Ticket.id).all()
    for start in range(0, len(rows), 64):
        chunk = rows[start : start + 64]
        vecs = embedder.embed([ticket_text(t.title, t.description) for t in chunk])
        for t, v in zip(chunk, vecs, strict=True):
            index.upsert(db, ticket_id=t.id, tenant_id=t.tenant_id, model=embedder.name, vector=v)
    db.flush()
    triaged = 0
    from app.agent import runner

    if payload.get("triage_open"):
        for t in rows:
            if t.status not in ("resolved", "closed"):
                runner.run(db, t, trigger="reindex")
                triaged += 1
    return {"embedded": len(rows), "triaged": triaged}
