"""
Knowledge base.

GET    /kb/documents                   list (requesters: published only)
POST   /kb/documents                   upload (multipart) → indexed in the background
GET    /kb/documents/{id}              one document + extracted text
PATCH  /kb/documents/{id}              title / visibility
POST   /kb/documents/{id}/reindex      re-chunk and re-embed
DELETE /kb/documents/{id}
GET    /kb/search?q=                   hybrid retrieval, no text generation
POST   /kb/answer                      grounded answer with citations (needs an LLM provider)
POST   /kb/queries/{id}/feedback       helpful / not helpful
GET    /tickets/{id}/ai/knowledge      articles related to a ticket (staff)
GET    /analytics/kb                   search / answer telemetry
"""

import time
from datetime import datetime, timedelta
from typing import Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import settings
from app.core.deps import get_org_user, org_id, require_permission
from app.core.limiter import limiter
from app.core.rbac import P, has_permission, is_staff
from app.db.database import get_db, utcnow
from app.db.models import KBDocument, KBQuery, User
from app.kb import answer as kb_answer
from app.kb import ingest
from app.kb.search import Hit, search
from app.services import audit
from app.services import tickets as ticket_svc

router = APIRouter(tags=["knowledge base"])


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    content_type: str
    visibility: str
    status: str
    error: str | None
    size_bytes: int
    chunk_count: int
    data_origin: str
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    text: str | None


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: Literal["internal", "public"] | None = None


class HitOut(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    heading: str | None
    snippet: str
    visibility: str
    score: float
    dense_similarity: float | None
    reranked: bool


class SearchOut(BaseModel):
    query_id: int | None
    mode: str
    hits: list[HitOut]


class AnswerIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class CitationOut(BaseModel):
    number: int
    chunk_id: int
    document_id: int
    title: str
    heading: str | None
    snippet: str


class AnswerOut(BaseModel):
    query_id: int | None
    status: Literal["answered", "no_answer", "search_only"]
    answer: str | None
    citations: list[CitationOut]
    supported_ratio: float | None
    unsupported_sentences: list[str]
    mode: str
    hits: list[HitOut]


class FeedbackIn(BaseModel):
    helpful: bool


def _hit(h: Hit) -> HitOut:
    return HitOut(
        chunk_id=h.chunk_id,
        document_id=h.document_id,
        title=h.title,
        heading=h.heading,
        snippet=h.content[:500],
        visibility=h.visibility,
        score=round(h.score, 4),
        dense_similarity=round(h.dense_similarity, 4) if h.dense_similarity is not None else None,
        reranked=h.reranked,
    )


def _public_only(user: User) -> bool:
    return not (is_staff(user.role) or has_permission(user.role, P.TICKETS_READ_ALL))


def _doc(db: Session, doc_id: int, user: User) -> KBDocument:
    doc = db.query(KBDocument).filter(KBDocument.id == doc_id, KBDocument.tenant_id == org_id(user)).first()
    if doc is None or (_public_only(user) and (doc.visibility != "public" or doc.status != "ready")):
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/kb/documents", response_model=list[DocumentOut])
def list_documents(user: User = Depends(require_permission(P.KB_READ)), db: Session = Depends(get_db)):
    q = db.query(KBDocument).filter(KBDocument.tenant_id == org_id(user))
    if _public_only(user):
        q = q.filter(KBDocument.visibility == "public", KBDocument.status == "ready")
    return q.order_by(KBDocument.updated_at.desc()).limit(500).all()


@router.post("/kb/documents", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("30/minute")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    visibility: Literal["internal", "public"] = Form(default="internal"),
    title: str | None = Form(default=None, max_length=200),
    user: User = Depends(require_permission(P.KB_MANAGE)),
    db: Session = Depends(get_db),
):
    data = file.file.read(settings.kb_max_upload_bytes + 1)
    try:
        doc = ingest.create_document(
            db, user=user, filename=file.filename or "document.txt", data=data, visibility=visibility, title=title
        )
    except ingest.KBError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
    audit.record(
        db,
        "kb.document.create",
        tenant_id=doc.tenant_id,
        actor=user,
        entity_type="kb_document",
        entity_id=doc.id,
        changes={"title": doc.title, "visibility": visibility, "bytes": len(data)},
    )
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/kb/documents/{doc_id}", response_model=DocumentDetailOut)
def get_document(doc_id: int, user: User = Depends(require_permission(P.KB_READ)), db: Session = Depends(get_db)):
    return _doc(db, doc_id, user)


@router.patch("/kb/documents/{doc_id}", response_model=DocumentOut)
def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    user: User = Depends(require_permission(P.KB_MANAGE)),
    db: Session = Depends(get_db),
):
    doc = _doc(db, doc_id, user)
    before = {"title": doc.title, "visibility": doc.visibility}
    if payload.title is not None:
        doc.title = payload.title.strip()
    if payload.visibility is not None:
        ingest.set_visibility(db, doc, payload.visibility)
    audit.record(
        db,
        "kb.document.update",
        tenant_id=doc.tenant_id,
        actor=user,
        entity_type="kb_document",
        entity_id=doc.id,
        changes=audit.diff(before, {"title": doc.title, "visibility": doc.visibility}),
    )
    if payload.title is not None and doc.status == "ready":
        # The title is part of every chunk's embedded text.
        ingest.jobs.enqueue(db, "kb.ingest", {"document_id": doc.id}, tenant_id=doc.tenant_id)
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/kb/documents/{doc_id}/reindex", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def reindex_document(doc_id: int, user: User = Depends(require_permission(P.KB_MANAGE)), db: Session = Depends(get_db)):
    doc = _doc(db, doc_id, user)
    doc.status = "processing"
    ingest.jobs.enqueue(db, "kb.ingest", {"document_id": doc.id}, tenant_id=doc.tenant_id)
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/kb/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: int, user: User = Depends(require_permission(P.KB_MANAGE)), db: Session = Depends(get_db)):
    doc = _doc(db, doc_id, user)
    audit.record(
        db,
        "kb.document.delete",
        tenant_id=doc.tenant_id,
        actor=user,
        entity_type="kb_document",
        entity_id=doc.id,
        changes={"title": doc.title},
    )
    db.delete(doc)
    db.commit()


@router.get("/kb/search", response_model=SearchOut)
@limiter.limit("60/minute")
def kb_search(
    request: Request,
    q: str = Query(min_length=2, max_length=1000),
    k: int = Query(default=5, ge=1, le=20),
    user: User = Depends(require_permission(P.KB_READ)),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    result = search(db, org_id(user), q, k=k, public_only=_public_only(user))
    row = kb_answer.log_search(db, user, q, result.mode, result.hits, started)
    db.commit()
    return SearchOut(query_id=row.id, mode=result.mode, hits=[_hit(h) for h in result.hits])


@router.post("/kb/answer", response_model=AnswerOut)
@limiter.limit("20/minute")
def kb_answer_endpoint(
    request: Request,
    payload: AnswerIn,
    user: User = Depends(require_permission(P.KB_READ)),
    db: Session = Depends(get_db),
):
    try:
        a = kb_answer.answer(db, user, payload.question, public_only=_public_only(user), provider=llm.get_llm())
    except llm.LLMError as e:
        db.commit()  # keep the ledger row of the failed call
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
    db.commit()
    return AnswerOut(
        query_id=a.query_id,
        status=cast(Literal["answered", "no_answer", "search_only"], a.status),
        answer=a.text,
        citations=[CitationOut(**c.__dict__) for c in a.citations],
        supported_ratio=a.supported_ratio,
        unsupported_sentences=a.unsupported_sentences,
        mode=a.retrieval_mode,
        hits=[_hit(h) for h in a.hits],
    )


@router.post("/kb/queries/{query_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def kb_feedback(query_id: int, payload: FeedbackIn, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    row = db.query(KBQuery).filter(KBQuery.id == query_id, KBQuery.user_id == user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Query not found")
    row.helpful = payload.helpful
    db.commit()


@router.get("/tickets/{ticket_id}/ai/knowledge", response_model=SearchOut)
def ticket_knowledge(
    ticket_id: int, user: User = Depends(require_permission(P.TICKETS_WORK)), db: Session = Depends(get_db)
):
    try:
        ticket = ticket_svc.get_visible_ticket(db, ticket_id, user)
    except ticket_svc.TicketError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from None
    result = search(db, ticket.tenant_id, f"{ticket.title}\n{ticket.description[:1000]}", k=5)
    hits = [h for h in result.hits if kb_answer.relevant(h)]
    return SearchOut(query_id=None, mode=result.mode, hits=[_hit(h) for h in hits])


class KBAnalyticsOut(BaseModel):
    window_days: int
    documents_ready: int
    chunks: int
    searches: int
    searches_without_results: int
    questions: int
    answered: int
    no_answer: int
    helpful: int
    not_helpful: int
    mean_supported_ratio: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None


@router.get("/analytics/kb", response_model=KBAnalyticsOut)
def kb_analytics(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(require_permission(P.ANALYTICS_READ)),
    db: Session = Depends(get_db),
):
    tid = org_id(user)
    rows = (
        db.query(KBQuery).filter(KBQuery.tenant_id == tid, KBQuery.created_at >= utcnow() - timedelta(days=days)).all()
    )
    lat = sorted(r.latency_ms for r in rows if r.latency_ms is not None)
    ratios = [r.supported_ratio for r in rows if r.supported_ratio is not None]
    docs = (
        db.query(func.count(KBDocument.id), func.coalesce(func.sum(KBDocument.chunk_count), 0))
        .filter(KBDocument.tenant_id == tid, KBDocument.status == "ready")
        .one()
    )
    return KBAnalyticsOut(
        window_days=days,
        documents_ready=int(docs[0]),
        chunks=int(docs[1]),
        searches=sum(r.mode == "search" for r in rows),
        searches_without_results=sum(r.mode == "search" and r.outcome == "no_results" for r in rows),
        questions=sum(r.mode == "answer" for r in rows),
        answered=sum(r.outcome == "answered" for r in rows),
        no_answer=sum(r.outcome == "no_answer" for r in rows),
        helpful=sum(r.helpful is True for r in rows),
        not_helpful=sum(r.helpful is False for r in rows),
        mean_supported_ratio=round(sum(ratios) / len(ratios), 3) if ratios else None,
        p50_latency_ms=lat[len(lat) // 2] if lat else None,
        p95_latency_ms=lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None,
    )
