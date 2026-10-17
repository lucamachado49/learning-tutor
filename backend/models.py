"""
models.py — Modelos ORM (SQLAlchemy 2.0).

Os tipos são portáveis (rodam em PostgreSQL e em SQLite nos testes).
Alterações de esquema devem ser feitas via Alembic:
    alembic -c backend/alembic.ini revision --autogenerate -m "descrição"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import config


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
    # Livros da biblioteca usados como base nesta sessão
    book_ids:   Mapped[list] = mapped_column(JSON, default=list)
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
    citations:  Mapped[list] = mapped_column(JSON, default=list)
    # Gabarito do exercício calculado pelo SymPy (oculto do aluno)
    answer_key: Mapped[str] = mapped_column(Text, default="")
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


class ConceptMastery(Base):
    """Domínio estimado do aluno por conceito (0–100), atualizado a cada avaliação."""

    __tablename__ = "concept_mastery"
    __table_args__ = (UniqueConstraint("domain", "norm", name="uq_mastery_domain_norm"),)

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    domain:     Mapped[str] = mapped_column(String(32), index=True)
    concept:    Mapped[str] = mapped_column(String(200))
    norm:       Mapped[str] = mapped_column(String(200))
    score:      Mapped[float] = mapped_column(Float, default=0.0)
    attempts:   Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --- Biblioteca ------------------------------------------------------------
class Book(Base):
    __tablename__ = "books"

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title:      Mapped[str] = mapped_column(String(300))
    filename:   Mapped[str] = mapped_column(String(300))
    domain:     Mapped[str] = mapped_column(String(32), default="")
    # queued → processing → ready | error  (a própria tabela funciona como fila)
    status:     Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress:   Mapped[float] = mapped_column(Float, default=0.0)
    error:      Mapped[str] = mapped_column(Text, default="")
    pages:      Mapped[int] = mapped_column(Integer, default=0)
    toc:        Mapped[list] = mapped_column(JSON, default=list)   # [[nível, título, página], ...]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", passive_deletes=True,
    )


class Chunk(Base):
    """Trecho do livro. A coluna de busca textual (tsv) existe só no PostgreSQL (ver migração)."""

    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_book_seq", "book_id", "seq"),)

    id:         Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    book_id:    Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    seq:        Mapped[int] = mapped_column(Integer)
    section:    Mapped[str] = mapped_column(Text, default="")    # "Cap. 3 › 3.2 Regra da cadeia"
    page_start: Mapped[int] = mapped_column(Integer)
    page_end:   Mapped[int] = mapped_column(Integer)
    kind:       Mapped[str] = mapped_column(String(16), default="text")   # text | exercise
    content:    Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(config.EMBED_DIM).with_variant(JSON(), "sqlite"), nullable=True)

    book: Mapped[Book] = relationship(back_populates="chunks")
