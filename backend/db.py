"""
db.py — Camada de acesso a dados: sessões, mensagens e memória do aluno.

As funções retornam dicts prontos para JSON, isolando o ORM do resto da API.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import config
import review
from models import ChatSession, ConceptMastery, Message, Mistake, utcnow

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_engine(url: str = config.DATABASE_URL) -> Engine:
    """Cria o engine (chamado no startup; os testes passam uma URL SQLite)."""
    global _engine, _SessionLocal
    if url.startswith("sqlite"):
        # SQLite em memória (testes): uma única conexão compartilhada entre threads
        _engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10,
                                connect_args={"connect_timeout": 10})
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        init_engine()
    s = _SessionLocal()  # type: ignore[misc]
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def ping() -> bool:
    try:
        with session_scope() as s:
            s.execute(select(1))
        return True
    except Exception:
        return False


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _session_dict(cs: ChatSession) -> dict:
    return {
        "id": cs.id, "title": cs.title, "domain": cs.domain,
        "language": cs.domain,  # compatibilidade com o frontend antigo
        "level": cs.level, "mode": cs.mode, "book_ids": cs.book_ids or [],
        "review_ids": cs.review_ids or [],
        "created_at": _iso(cs.created_at), "updated_at": _iso(cs.updated_at),
    }


def _message_dict(m: Message) -> dict:
    return {
        "id": m.id, "session_id": m.session_id, "role": m.role, "content": m.content,
        "feedback": m.feedback, "provider": m.provider, "citations": m.citations or [],
        "verified": bool(m.answer_key),
        "created_at": _iso(m.created_at),
    }


def _mistake_dict(m: Mistake) -> dict:
    return {
        "id": m.id, "domain": m.domain, "text": m.text, "count": m.count,
        "first_seen": _iso(m.first_seen), "last_seen": _iso(m.last_seen),
    }


# --- Sessões ---------------------------------------------------------------
def list_sessions(limit: int = 100) -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit))
        return [_session_dict(r) for r in rows]


def get_session(session_id: str) -> Optional[dict]:
    with session_scope() as s:
        cs = s.get(ChatSession, session_id)
        return _session_dict(cs) if cs else None


def create_session(domain: str, level: str, mode: str, book_ids: Optional[list[str]] = None) -> dict:
    with session_scope() as s:
        cs = ChatSession(domain=domain, level=level, mode=mode, book_ids=book_ids or [])
        s.add(cs)
        s.flush()
        return _session_dict(cs)


def update_session(session_id: str, **fields) -> None:
    with session_scope() as s:
        cs = s.get(ChatSession, session_id)
        if cs is None:
            return
        for key, value in fields.items():
            setattr(cs, key, value)
        cs.updated_at = utcnow()


def delete_session(session_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(Message).where(Message.session_id == session_id))
        s.execute(delete(ChatSession).where(ChatSession.id == session_id))


# --- Mensagens -------------------------------------------------------------
def get_messages(session_id: str, limit: Optional[int] = None) -> list[dict]:
    with session_scope() as s:
        q = select(Message).where(Message.session_id == session_id).order_by(Message.seq.desc())
        if limit:
            q = q.limit(limit)
        rows = list(s.scalars(q))
        return [_message_dict(m) for m in reversed(rows)]


def add_message(
    session_id: str, role: str, content: str, feedback: str = "", provider: str = "",
    citations: Optional[list[dict]] = None, answer_key: str = "",
) -> str:
    with session_scope() as s:
        last = s.scalar(select(func.max(Message.seq)).where(Message.session_id == session_id)) or 0
        m = Message(session_id=session_id, seq=last + 1, role=role, content=content,
                    feedback=feedback, provider=provider, citations=citations or [],
                    answer_key=answer_key)
        s.add(m)
        s.flush()
        return m.id


def last_answer_key(session_id: str) -> str:
    """Gabarito do exercício mais recente da sessão (se a última fala do tutor tiver um)."""
    with session_scope() as s:
        last = s.scalar(
            select(Message).where(Message.session_id == session_id, Message.role == "assistant")
            .order_by(Message.seq.desc()).limit(1)
        )
        return last.answer_key if last else ""


# --- Memória do aluno ------------------------------------------------------
def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def record_mistakes(domain: str, items: list[str]) -> None:
    now = utcnow()
    with session_scope() as s:
        for text in items:
            norm = _normalize(text)
            existing = s.scalar(select(Mistake).where(Mistake.domain == domain, Mistake.norm == norm))
            if existing:
                existing.count += 1
                existing.last_seen = now
            else:
                s.add(Mistake(domain=domain, text=text, norm=norm, first_seen=now, last_seen=now))
                s.flush()
                review.on_new_mistake(s, domain, text)


def top_mistakes(domain: str, limit: int = 10) -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(
            select(Mistake).where(Mistake.domain == domain)
            .order_by(Mistake.count.desc(), Mistake.last_seen.desc()).limit(limit)
        )
        return [_mistake_dict(m) for m in rows]


def delete_mistake(mistake_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(Mistake).where(Mistake.id == mistake_id))


# --- Mapa de domínio por conceito -----------------------------------------
MASTERY_ALPHA = 0.4  # peso da avaliação mais recente na média móvel


def record_mastery(domain: str, scores: list[tuple[str, float]]) -> None:
    now = utcnow()
    with session_scope() as s:
        for concept, score in scores:
            score = max(0.0, min(100.0, score))
            norm = _normalize(concept)[:200]
            row = s.scalar(select(ConceptMastery).where(
                ConceptMastery.domain == domain, ConceptMastery.norm == norm))
            if row:
                row.score = (1 - MASTERY_ALPHA) * row.score + MASTERY_ALPHA * score
                row.attempts += 1
                row.updated_at = now
            else:
                row = ConceptMastery(domain=domain, concept=concept[:200], norm=norm,
                                     score=score, attempts=1, updated_at=now)
                s.add(row)
                s.flush()
            review.on_mastery_update(s, domain, row.concept, norm, row.score)


def get_mastery(domain: str, limit: int = 50) -> list[dict]:
    """Conceitos ordenados do mais fraco para o mais forte."""
    with session_scope() as s:
        rows = s.scalars(
            select(ConceptMastery).where(ConceptMastery.domain == domain)
            .order_by(ConceptMastery.score.asc(), ConceptMastery.updated_at.desc()).limit(limit)
        )
        return [{"id": r.id, "concept": r.concept, "score": r.score, "attempts": r.attempts,
                 "updated_at": _iso(r.updated_at)} for r in rows]


def delete_mastery(item_id: str) -> None:
    with session_scope() as s:
        s.execute(delete(ConceptMastery).where(ConceptMastery.id == item_id))


# --- Revisão espaçada ------------------------------------------------------
def due_review_ids(domain: str, kinds: tuple = ("mistake", "concept"), limit: int = 5) -> list[str]:
    from models import ReviewItem
    with session_scope() as s:
        review.sync_existing(s, domain)
        end = utcnow().replace(hour=23, minute=59, second=59)
        return list(s.scalars(
            select(ReviewItem.id).where(ReviewItem.domain == domain, ReviewItem.kind.in_(kinds),
                                        ReviewItem.due_at <= end)
            .order_by(ReviewItem.due_at).limit(limit)
        ))


def review_today(domain: str) -> dict:
    with session_scope() as s:
        return review.today(s, domain)


def review_progress(domain: str, days: int = 30) -> dict:
    with session_scope() as s:
        return review.progress(s, domain, days)


def grade_review(item_id: str, quality: int) -> bool:
    from models import ReviewItem
    with session_scope() as s:
        item = s.get(ReviewItem, item_id)
        if item is None:
            return False
        review.grade_item(s, item, quality)
        return True


def grade_review_by_label(domain: str, label: str, quality: int) -> bool:
    with session_scope() as s:
        return review.grade_by_label(s, domain, label, quality)


def review_items_by_ids(ids: list[str]) -> list[dict]:
    from models import ReviewItem
    with session_scope() as s:
        rows = [s.get(ReviewItem, i) for i in ids]
        return [review._item_dict(r) for r in rows if r]
