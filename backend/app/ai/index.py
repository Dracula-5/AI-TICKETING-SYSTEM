"""
Ticket vector index. PostgreSQL uses pgvector's cosine-distance operator with
an HNSW index; SQLite (test tier) falls back to an exact NumPy scan. In both,
the tenant filter is part of the same query — similarity search cannot return
another organization's tickets.
"""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import utcnow
from app.db.models import TicketEmbedding

# HNSW returns at most ef_search candidates, and the tenant filter is applied
# to those candidates afterwards. Without these settings a LIMIT 60 query gets
# at most 40 rows (the default ef_search), and fewer still for a small tenant
# in a shared table. Iterative scans (pgvector >= 0.8) keep searching until the
# filtered LIMIT is met; strict_order keeps results exactly ordered.
HNSW_EF_SEARCH = 100
HNSW_ITERATIVE_SCAN = "strict_order"


@dataclass
class Neighbor:
    ticket_id: int
    similarity: float


def upsert(db: Session, *, ticket_id: int, tenant_id: int, model: str, vector: np.ndarray) -> None:
    row = db.get(TicketEmbedding, ticket_id)
    if row is None:
        db.add(TicketEmbedding(ticket_id=ticket_id, tenant_id=tenant_id, model=model, embedding=vector.tolist()))
    else:
        row.model, row.embedding, row.created_at = model, vector.tolist(), utcnow()
    db.flush()


def search(
    db: Session, *, tenant_id: int, vector: np.ndarray, model: str, k: int, exclude_ticket_id: int | None = None
) -> list[Neighbor]:
    if db.get_bind().dialect.name == "postgresql":
        # SET LOCAL lasts until the end of the current transaction only.
        db.execute(text(f"SET LOCAL hnsw.ef_search = {int(max(HNSW_EF_SEARCH, k))}"))
        db.execute(text(f"SET LOCAL hnsw.iterative_scan = {HNSW_ITERATIVE_SCAN}"))
        rows = db.execute(
            text(
                "SELECT ticket_id, 1 - (embedding <=> CAST(:q AS vector)) AS similarity "
                "FROM ticket_embeddings "
                "WHERE tenant_id = :tenant AND model = :model AND ticket_id <> :exclude "
                "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
            ),
            {
                "q": "[" + ",".join(f"{x:.6f}" for x in vector) + "]",
                "tenant": tenant_id,
                "model": model,
                "exclude": exclude_ticket_id or -1,
                "k": k,
            },
        ).all()
        return [Neighbor(int(r[0]), float(r[1])) for r in rows]

    rows = (
        db.query(TicketEmbedding.ticket_id, TicketEmbedding.embedding)
        .filter(TicketEmbedding.tenant_id == tenant_id, TicketEmbedding.model == model)
        .all()
    )
    rows = [r for r in rows if r[0] != exclude_ticket_id]
    if not rows:
        return []
    matrix = np.asarray([r[1] for r in rows], dtype=np.float32)
    sims = matrix @ vector.astype(np.float32)
    order = np.argsort(-sims)[:k]
    return [Neighbor(int(rows[i][0]), float(sims[i])) for i in order]
