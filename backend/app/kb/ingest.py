"""Knowledge-base ingestion: upload → extract → chunk → embed, in the worker."""

import hashlib

from sqlalchemy.orm import Session

from app.ai.embedder import get_embedder
from app.core.config import settings
from app.db.models import KBChunk, KBDocument, User
from app.kb import parsing
from app.kb.search import chunk_text
from app.services import jobs

EMBED_BATCH = 64


class KBError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_document(
    db: Session,
    *,
    user: User,
    filename: str,
    data: bytes,
    visibility: str,
    title: str | None = None,
    data_origin: str = "real",
) -> KBDocument:
    if visibility not in ("internal", "public"):
        raise KBError("visibility must be 'internal' or 'public'", 422)
    if len(data) > settings.kb_max_upload_bytes:
        raise KBError(f"File too large (limit {settings.kb_max_upload_bytes // (1024 * 1024)} MB)", 413)
    try:
        ctype, text = parsing.extract(filename, data)  # validate synchronously: fail fast on bad files
    except parsing.ParseError as e:
        raise KBError(str(e), 422) from None
    doc = KBDocument(
        tenant_id=user.tenant_id,
        title=(title or parsing.title_from(filename, text)).strip()[:200],
        filename=filename[:255],
        content_type=ctype,
        visibility=visibility,
        status="processing",
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        text=text,
        created_by_user_id=user.id,
        data_origin=data_origin,
    )
    db.add(doc)
    db.flush()
    jobs.enqueue(db, "kb.ingest", {"document_id": doc.id}, tenant_id=doc.tenant_id, dedupe_key=f"kb.ingest:{doc.id}")
    return doc


def index_document(db: Session, doc: KBDocument) -> int:
    embedder = get_embedder()
    if embedder is None:
        raise KBError("Embeddings are disabled; the document cannot be indexed", 503)
    chunks = parsing.chunk(doc.text or "")
    db.query(KBChunk).filter(KBChunk.document_id == doc.id).delete(synchronize_session=False)
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        vecs = embedder.embed([chunk_text(doc.title, c.heading, c.content) for c in batch])
        for c, v in zip(batch, vecs, strict=True):
            db.add(
                KBChunk(
                    tenant_id=doc.tenant_id,
                    document_id=doc.id,
                    ordinal=c.ordinal,
                    heading=c.heading,
                    content=c.content,
                    visibility=doc.visibility,
                    model=embedder.name,
                    embedding=v.tolist(),
                )
            )
    doc.chunk_count, doc.status, doc.error = len(chunks), "ready", None
    db.flush()
    return len(chunks)


@jobs.handler("kb.ingest")
def ingest_job(db: Session, payload: dict) -> dict:
    doc = db.get(KBDocument, payload["document_id"])
    if doc is None:
        return {"skipped": "document deleted"}
    try:
        n = index_document(db, doc)
    except KBError as e:
        doc.status, doc.error = "failed", e.message[:500]
        return {"failed": e.message}
    return {"chunks": n}


def set_visibility(db: Session, doc: KBDocument, visibility: str) -> None:
    if visibility not in ("internal", "public"):
        raise KBError("visibility must be 'internal' or 'public'", 422)
    doc.visibility = visibility
    db.query(KBChunk).filter(KBChunk.document_id == doc.id).update({KBChunk.visibility: visibility})
