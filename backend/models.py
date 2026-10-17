"""
models.py — Modelos ORM (SQLAlchemy 2.0).

Os tipos são portáveis (rodam em PostgreSQL e em SQLite nos testes).
Alterações de esquema devem ser feitas via Alembic:
    alembic -c backend/alembic.ini revision --autogenerate -m "descrição"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "sessions"

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title:      Mapped[str] = mapped_column(String(200), default="Nova Conversa")
    domain:     Mapped[str] = mapped_column(String(32), index=True)
    level:      Mapped[str] = mapped_column(String(32))
    mode:       Mapped[str] = mapped_column(String(32), default="conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    # Ordem dentro da sessão (timestamps podem empatar no Windows)
    seq:        Mapped[int] = mapped_column(Integer, default=0)
    role:       Mapped[str] = mapped_column(String(16))
    content:    Mapped[str] = mapped_column(Text)
    feedback:   Mapped[str] = mapped_column(Text, default="")
    provider:   Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    session: Mapped[ChatSession] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_session_seq", "session_id", "seq"),)


class Mistake(Base):
    """Erro/lacuna recorrente do aluno (memória de longo prazo por domínio)."""

    __tablename__ = "mistakes"
    __table_args__ = (UniqueConstraint("domain", "norm", name="uq_mistakes_domain_norm"),)

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    domain:     Mapped[str] = mapped_column(String(32), index=True)
    text:       Mapped[str] = mapped_column(Text)
    norm:       Mapped[str] = mapped_column(Text)
    count:      Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
