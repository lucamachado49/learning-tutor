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
from models import ChatSession, Message, Mistake, utcnow

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_engine(url: str = config.DATABASE_URL) -> Engine:
    """Cria o engine (chamado no startup; os testes passam uma URL SQLite)."""
    global _engine, _SessionLocal
    if url.startswith("sqlite"):
        # SQLite em memória (testes): uma única conexão compartilhada entre threads
        _engine = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
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
        "level": cs.level, "mode": cs.mode,
        "created_at": _iso(cs.created_at), "updated_at": _iso(cs.updated_at),
    }


def _message_dict(m: Message) -> dict:
    return {
        "id": m.id, "session_id": m.session_id, "role": m.role, "content": m.content,
        "feedback": m.feedback, "provider": m.provider, "created_at": _iso(m.created_at),
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


def create_session(domain: str, level: str, mode: str) -> dict:
    with session_scope() as s:
        cs = ChatSession(domain=domain, level=level, mode=mode)
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


def add_message(session_id: str, role: str, content: str, feedback: str = "", provider: str = "") -> str:
    with session_scope() as s:
        last = s.scalar(select(func.max(Message.seq)).where(Message.session_id == session_id)) or 0
        m = Message(session_id=session_id, seq=last + 1, role=role, content=content,
                    feedback=feedback, provider=provider)
        s.add(m)
        s.flush()
        return m.id


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
