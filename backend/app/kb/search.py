"""
Hybrid knowledge-base retrieval: dense (pgvector) + lexical (PostgreSQL full-
text search) fused with Reciprocal Rank Fusion, optionally re-scored by a
cross-encoder. Every query filters by tenant (and, for requesters, by
visibility) inside the SQL — retrieval cannot return another organization's
text. SQLite (test tier) uses an exact NumPy scan and an in-process BM25.
"""

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.embedder import get_embedder
from app.core.config import settings
from app.db.models import KBChunk, KBDocument

CANDIDATES = 30  # per retriever, before fusion
RRF_K = 60
RERANK_TOP = 20
# Weight of the full-text ranking when dense retrieval found something relevant. Chosen on the
# validation half of CQADupStack (reports/rag/fusion_weight.md): 0.0 (nDCG@10 0.419 vs 0.377 for
# equal-weight RRF). Lexical still ranks alone when dense finds nothing above DENSE_FLOOR.
LEXICAL_WEIGHT = 0.0
DENSE_FLOOR = 0.35


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    heading: str | None
    content: str
    visibility: str
    score: float  # RRF score, or cross-encoder score when reranked
    dense_similarity: float | None = None
    lexical_rank: int | None = None
    dense_rank: int | None = None
    reranked: bool = False


@dataclass
class SearchResult:
    hits: list[Hit]
    mode: str  # hybrid | hybrid+rerank | dense | lexical
    timings_ms: dict[str, float] = field(default_factory=dict)


def chunk_text(title: str, heading: str | None, content: str) -> str:
    """What gets embedded: the document title and section heading give short
    passages the context they lack on their own."""
    head = f"{title} — {heading}" if heading and heading != title else title
    return f"{head}\n{content}"


# --- dense ------------------------------------------------------------------


def _dense(db: Session, tenant_id: int, vec: np.ndarray, model: str, public_only: bool, k: int):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(f"SET LOCAL hnsw.ef_search = {max(100, k)}"))
        db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        rows = db.execute(
            text(
                "SELECT id, 1 - (embedding <=> CAST(:q AS vector)) FROM kb_chunks "
                "WHERE tenant_id = :t AND model = :m AND (NOT :public_only OR visibility = 'public') "
                "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
            ),
            {
                "q": "[" + ",".join(f"{x:.6f}" for x in vec) + "]",
                "t": tenant_id,
                "m": model,
                "k": k,
                "public_only": public_only,
            },
        ).all()
        return [(int(r[0]), float(r[1])) for r in rows]
    q = db.query(KBChunk.id, KBChunk.embedding).filter(KBChunk.tenant_id == tenant_id, KBChunk.model == model)
    if public_only:
        q = q.filter(KBChunk.visibility == "public")
    rows = q.all()
    if not rows:
        return []
    sims = np.asarray([r[1] for r in rows], dtype=np.float32) @ vec.astype(np.float32)
    order = np.argsort(-sims)[:k]
    return [(int(rows[i][0]), float(sims[i])) for i in order]


# --- lexical ----------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")
# fmt: off
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how", "i", "in",
    "is", "it", "my", "of", "on", "or", "our", "so", "the", "this", "to", "was", "what", "when", "where",
    "which", "who", "why", "will", "with", "you", "your",
})
# fmt: on


def tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if t not in _STOP and len(t) > 1]


def _lexical(db: Session, tenant_id: int, query: str, public_only: bool, k: int):
    if db.get_bind().dialect.name == "postgresql":
        rows = db.execute(
            text(
                "SELECT id FROM kb_chunks, websearch_to_tsquery('english', :q) query "
                "WHERE tenant_id = :t AND (NOT :public_only OR visibility = 'public') AND tsv @@ query "
                "ORDER BY ts_rank_cd(tsv, query) DESC LIMIT :k"
            ),
            {"q": query, "t": tenant_id, "k": k, "public_only": public_only},
        ).all()
        if rows or not tokens(query):
            return [int(r[0]) for r in rows]
        # websearch_to_tsquery ANDs terms; fall back to OR for long natural-language questions.
        rows = db.execute(
            text(
                "SELECT id FROM kb_chunks, to_tsquery('english', :q) query "
                "WHERE tenant_id = :t AND (NOT :public_only OR visibility = 'public') AND tsv @@ query "
                "ORDER BY ts_rank_cd(tsv, query) DESC LIMIT :k"
            ),
            {"q": " | ".join(tokens(query)), "t": tenant_id, "k": k, "public_only": public_only},
        ).all()
        return [int(r[0]) for r in rows]
    q = db.query(KBChunk.id, KBChunk.heading, KBChunk.content).filter(KBChunk.tenant_id == tenant_id)
    if public_only:
        q = q.filter(KBChunk.visibility == "public")
    docs = [(r[0], tokens(f"{r[1] or ''} {r[2]}")) for r in q.all()]
    return [cid for cid, _ in bm25(tokens(query), docs)[:k]]


def bm25(query: list[str], docs: list[tuple[int, list[str]]], k1: float = 1.5, b: float = 0.75):
    if not docs or not query:
        return []
    n = len(docs)
    avgdl = sum(len(d) for _, d in docs) / n or 1.0
    df = Counter(t for _, d in docs for t in set(d))
    scored = []
    for cid, d in docs:
        tf, score = Counter(d), 0.0
        for t in set(query):
            if tf[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        if score > 0:
            scored.append((cid, score))
    return sorted(scored, key=lambda x: -x[1])


# --- reranking --------------------------------------------------------------

_rerank_lock = threading.Lock()
_reranker = None


def get_reranker():
    """Cross-encoder (FastEmbed ONNX) or None when disabled/unavailable."""
    global _reranker
    name = settings.kb_rerank_model
    if not name or name == "none":
        return None
    with _rerank_lock:
        if _reranker is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                _reranker = TextCrossEncoder(model_name=name, cache_dir=settings.model_cache_dir or None)
            except Exception:  # model missing offline, etc. — hybrid results still work
                return None
        return _reranker


def rrf(rankings: list[list[int]], k: int = RRF_K, weights: list[float] | None = None) -> dict[int, float]:
    scores: dict[int, float] = {}
    for i, ranking in enumerate(rankings):
        w = 1.0 if weights is None else weights[i]
        if w <= 0:
            continue
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank)
    return scores


def search(
    db: Session, tenant_id: int, query: str, *, k: int = 5, public_only: bool = False, rerank: bool = True
) -> SearchResult:
    query = query.strip()[:1000]
    timings: dict[str, float] = {}
    if not query:
        return SearchResult([], "dense", timings)
    embedder = get_embedder()
    t0 = time.perf_counter()
    dense = []
    if embedder is not None:
        vec = embedder.embed([query])[0]
        timings["embed"] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        dense = _dense(db, tenant_id, vec, embedder.name, public_only, CANDIDATES)
        timings["dense"] = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    lexical = _lexical(db, tenant_id, query, public_only, CANDIDATES)
    timings["lexical"] = (time.perf_counter() - t0) * 1000

    dense_ids = [cid for cid, _ in dense]
    # Dense-first (P6b chose the lexical weight on validation: w = 0). Full-text results take
    # over only when no dense hit clears the relevance floor — e.g. exact error codes.
    dense_relevant = any(sim >= DENSE_FLOOR for _, sim in dense)
    if dense_relevant:
        fused, mode = rrf([dense_ids, lexical], weights=[1.0, LEXICAL_WEIGHT]), "dense"
    else:
        fused, mode = rrf([lexical, dense_ids], weights=[1.0, LEXICAL_WEIGHT]), "lexical-fallback"
    if not fused:
        return SearchResult([], mode, timings)
    order = sorted(fused, key=lambda cid: -fused[cid])[: max(k, RERANK_TOP)]
    rows = {
        c.id: (c, d)
        for c, d in db.query(KBChunk, KBDocument)
        .join(KBDocument, KBDocument.id == KBChunk.document_id)
        .filter(KBChunk.id.in_(order), KBChunk.tenant_id == tenant_id, KBDocument.status == "ready")
    }
    sim = dict(dense)
    hits = [
        Hit(
            chunk_id=cid,
            document_id=rows[cid][1].id,
            title=rows[cid][1].title,
            heading=rows[cid][0].heading,
            content=rows[cid][0].content,
            visibility=rows[cid][0].visibility,
            score=fused[cid],
            dense_similarity=sim.get(cid),
            dense_rank=dense_ids.index(cid) + 1 if cid in sim else None,
            lexical_rank=lexical.index(cid) + 1 if cid in lexical else None,
        )
        for cid in order
        if cid in rows
    ]
    reranker = get_reranker() if rerank else None
    if reranker is not None and hits:
        t0 = time.perf_counter()
        scores = list(reranker.rerank(query, [chunk_text(h.title, h.heading, h.content) for h in hits]))
        for h, s in zip(hits, scores, strict=True):
            h.score, h.reranked = float(s), True
        hits.sort(key=lambda h: -h.score)
        timings["rerank"] = (time.perf_counter() - t0) * 1000
        mode += "+rerank"
    return SearchResult(hits[:k], mode, timings)
