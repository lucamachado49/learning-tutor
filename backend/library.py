"""
library.py — Biblioteca de livros (RAG): importação de PDF, embeddings e busca híbrida.

Fluxo de importação (executado pelo worker em segundo plano):
    PDF → páginas em markdown (PyMuPDF) → sumário (TOC) → trechos por seção
        → embeddings (bge-m3 via Ollama) → tabela chunks (pgvector + tsvector)

A busca combina similaridade vetorial e busca textual com Reciprocal Rank Fusion.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import delete, select, text, update

import config
import db
import reranker
from models import Book, Chunk

log = logging.getLogger("tutor.library")

# Aplicado só ao título mais específico da seção ("Part II ... Problems" não é exercício)
EXERCISE_RE = re.compile(r"exerc|^\W*(?:\d[\d.]*\s*)?problems?(?:\s+(?:and|&)\s+solutions?)?\s*$|ejercicio|quest[õo]es|drill", re.IGNORECASE)


def is_exercise_section(section: str) -> bool:
    leaf = section.split(" › ")[-1] if section else ""
    return bool(EXERCISE_RE.search(leaf))


# ---------------------------------------------------------------------------
# Extração e divisão em trechos (funções puras — testáveis sem banco)
# ---------------------------------------------------------------------------
@dataclass
class ChunkDraft:
    section: str
    page_start: int
    page_end: int
    kind: str
    content: str
    parts: list[str] = field(default_factory=list)


def section_for_page(toc: list[list], page: int) -> str:
    """Caminho da seção ativa numa página, ex.: 'Cap. 3 Cálculo › 3.2 Regra da cadeia'."""
    path: dict[int, str] = {}
    for level, title, start in toc:
        if start > page:
            break
        path[level] = title.strip()
        for deeper in [lvl for lvl in path if lvl > level]:
            del path[deeper]
    return " › ".join(path[k] for k in sorted(path))


def split_into_chunks(pages: list[tuple[int, str]], toc: list[list], max_chars: int) -> list[ChunkDraft]:
    """Agrupa parágrafos em trechos de até max_chars, sem misturar seções diferentes."""
    chunks: list[ChunkDraft] = []
    cur: Optional[ChunkDraft] = None

    def flush():
        nonlocal cur
        if cur and cur.parts:
            cur.content = "\n\n".join(cur.parts).strip()
            if cur.content:
                chunks.append(cur)
        cur = None

    for page_no, page_text in pages:
        section = section_for_page(toc, page_no)
        kind = "exercise" if is_exercise_section(section) else "text"
        if cur and cur.section != section:
            flush()
        for para in re.split(r"\n\s*\n", page_text):
            para = para.strip()
            if not para:
                continue
            # Parágrafo gigante (ex.: tabela): corta em pedaços
            pieces = [para[i:i + max_chars] for i in range(0, len(para), max_chars)]
            for piece in pieces:
                if cur and sum(len(p) for p in cur.parts) + len(piece) > max_chars:
                    flush()
                if cur is None:
                    cur = ChunkDraft(section, page_no, page_no, kind, "")
                cur.parts.append(piece)
                cur.page_end = page_no
    flush()
    return chunks


def extract_pdf(path: Path) -> tuple[list[tuple[int, str]], list[list], int, str]:
    """Retorna (páginas [(nº, markdown)], toc, total_de_páginas, título)."""
    import pymupdf
    import pymupdf4llm

    doc = pymupdf.open(path)
    toc = [[lvl, title, page] for lvl, title, page in doc.get_toc(simple=True)]
    title = (doc.metadata or {}).get("title") or path.stem
    page_dicts = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
    pages = [(i + 1, d.get("text", "")) for i, d in enumerate(page_dicts)]
    total = doc.page_count
    doc.close()
    return pages, toc, total, title


# ---------------------------------------------------------------------------
# Embeddings (Ollama)
# ---------------------------------------------------------------------------
def embed(texts: list[str], timeout: float = 120.0) -> list[list[float]]:
    r = httpx.post(
        f"{config.OLLAMA_BASE_URL}/api/embed",
        json={"model": config.EMBED_MODEL, "input": texts},
        timeout=timeout,
    )
    if r.status_code == 404:
        raise RuntimeError(f"Modelo de embeddings ausente. Execute: ollama pull {config.EMBED_MODEL}")
    r.raise_for_status()
    return r.json()["embeddings"]


# ---------------------------------------------------------------------------
# Importação (worker)
# ---------------------------------------------------------------------------
def book_path(book_id: str) -> Path:
    return config.BOOKS_DIR / f"{book_id}.pdf"


def _set(book_id: str, **fields) -> None:
    with db.session_scope() as s:
        s.execute(update(Book).where(Book.id == book_id).values(**fields))


def ingest_book(book_id: str) -> None:
    """Processa um livro já marcado como 'processing'. Erros ficam registrados no livro."""
    try:
        pages, toc, total, pdf_title = extract_pdf(book_path(book_id))
        _set(book_id, pages=total, toc=toc, progress=0.15)
        with db.session_scope() as s:
            book = s.get(Book, book_id)
            if book and book.title == book.filename and pdf_title:
                book.title = pdf_title[:300]

        drafts = split_into_chunks(pages, toc, config.CHUNK_CHARS)
        if not drafts:
            raise RuntimeError("Nenhum texto extraído (PDF escaneado? precisa de OCR).")

        with db.session_scope() as s:
            s.execute(delete(Chunk).where(Chunk.book_id == book_id))

        batch = 16
        for i in range(0, len(drafts), batch):
            part = drafts[i:i + batch]
            vectors = embed([f"{d.section}\n{d.content}" for d in part])
            with db.session_scope() as s:
                for j, (d, vec) in enumerate(zip(part, vectors)):
                    s.add(Chunk(
                        book_id=book_id, seq=i + j, section=d.section, page_start=d.page_start,
                        page_end=d.page_end, kind=d.kind, content=d.content, embedding=vec,
                    ))
            _set(book_id, progress=round(0.15 + 0.85 * (i + len(part)) / len(drafts), 3))

        _set(book_id, status="ready", progress=1.0, error="")
        log.info("Livro %s importado: %d trechos", book_id, len(drafts))
    except Exception as exc:
        log.exception("Falha ao importar livro %s", book_id)
        _set(book_id, status="error", error=str(exc)[:1000])


def _claim_next() -> Optional[str]:
    """Pega o próximo livro da fila de forma segura entre vários workers."""
    with db.session_scope() as s:
        row = s.execute(text("""
            UPDATE books SET status = 'processing', progress = 0.05
            WHERE id = (
                SELECT id FROM books WHERE status = 'queued'
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
            )
            RETURNING id
        """)).first()
        return row[0] if row else None


async def worker_loop(poll_seconds: float = 3.0) -> None:
    # Recuperação após queda: o que estava em processamento volta para a fila
    with db.session_scope() as s:
        s.execute(update(Book).where(Book.status == "processing").values(status="queued"))

    while True:
        try:
            book_id = await asyncio.to_thread(_claim_next)
            if book_id:
                await asyncio.to_thread(ingest_book, book_id)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Erro no worker da biblioteca")
        await asyncio.sleep(poll_seconds)


# ---------------------------------------------------------------------------
# Busca híbrida
# ---------------------------------------------------------------------------
_HYBRID_SQL = text("""
WITH v AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS r
    FROM chunks
    WHERE book_id = ANY(:ids) AND (:kind = '' OR kind = :kind)
    ORDER BY embedding <=> CAST(:qvec AS vector)
    LIMIT 30
), t AS (
    SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, q) DESC) AS r
    FROM chunks, to_tsquery('simple', :tsq) AS q
    WHERE :tsq <> '' AND book_id = ANY(:ids) AND (:kind = '' OR kind = :kind) AND tsv @@ q
    ORDER BY ts_rank_cd(tsv, q) DESC
    LIMIT 30
)
SELECT c.id, c.book_id, b.title AS book, c.section, c.page_start, c.page_end, c.kind, c.content,
       COALESCE(1.0 / (60 + v.r), 0) + COALESCE(1.0 / (60 + t.r), 0) AS score,
       1 - (c.embedding <=> CAST(:qvec AS vector)) AS vsim
FROM (SELECT id FROM v UNION SELECT id FROM t) u
JOIN chunks c ON c.id = u.id
JOIN books b ON b.id = c.book_id
LEFT JOIN v ON v.id = u.id
LEFT JOIN t ON t.id = u.id
ORDER BY score DESC
LIMIT :k
""")


def build_tsquery(query: str) -> str:
    """Termos com 3+ letras unidos por OR (seguro: só caracteres de palavra)."""
    words = dict.fromkeys(w.lower() for w in re.findall(r"\w{3,}", query))
    return " | ".join(words)


def search(query: str, book_ids: list[str], k: int = config.RAG_TOP_K, kind: str = "",
           rerank: bool = True) -> list[dict]:
    """Busca híbrida (vetor + BM25 + RRF) → reranker cross-encoder → top-k."""
    if not book_ids or not query.strip():
        return []
    qvec = embed([query])[0]
    pool = max(k, config.RERANK_CANDIDATES) if rerank else k
    with db.session_scope() as s:
        rows = s.execute(_HYBRID_SQL, {
            "qvec": "[" + ",".join(f"{x:.6f}" for x in qvec) + "]",
            "tsq": build_tsquery(query), "ids": book_ids, "kind": kind, "k": pool,
        }).mappings().all()
    candidates = [dict(r) for r in rows]
    return reranker.rerank(query, candidates, k) if rerank else candidates


def is_relevant(results: list[dict]) -> bool:
    """Algum trecho é de fato sobre a pergunta? (base da recusa calibrada)

    Usa a similaridade do bge-m3 — alinhada entre línguas. A nota do reranker NÃO serve para
    isso: pergunta em português sobre livro em inglês recebe nota baixa mesmo quando relevante.
    Medido (4 livros): fora de tema 0,38–0,45; relevantes 0,48–0,70.
    """
    sims = [r["vsim"] for r in results if r.get("vsim") is not None]
    return not sims or max(sims) >= config.RELEVANCE_MIN_SIM


def toc_outline(book_ids: list[str], max_level: int = 2, max_lines: int = 160) -> str:
    """Sumário compacto dos livros, para o LLM montar roadmaps."""
    lines: list[str] = []
    with db.session_scope() as s:
        for book in s.scalars(select(Book).where(Book.id.in_(book_ids))):
            lines.append(f"# {book.title}")
            for level, title, page in book.toc or []:
                if level <= max_level:
                    lines.append(f"{'  ' * (level - 1)}- {title} (p. {page})")
    return "\n".join(lines[:max_lines])


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def _book_dict(b: Book) -> dict:
    return {
        "id": b.id, "title": b.title, "filename": b.filename, "domain": b.domain,
        "status": b.status, "progress": b.progress, "error": b.error, "pages": b.pages,
        "chapters": sum(1 for lvl, *_ in (b.toc or []) if lvl == 1),
        "created_at": b.created_at.isoformat(),
    }


def create_book(filename: str, data: bytes, domain: str = "") -> dict:
    config.BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    with db.session_scope() as s:
        book = Book(title=filename, filename=filename, domain=domain)
        s.add(book)
        s.flush()
        book_path(book.id).write_bytes(data)
        return _book_dict(book)


def list_books() -> list[dict]:
    with db.session_scope() as s:
        return [_book_dict(b) for b in s.scalars(select(Book).order_by(Book.created_at.desc()))]


def get_book(book_id: str) -> Optional[dict]:
    with db.session_scope() as s:
        b = s.get(Book, book_id)
        return {**_book_dict(b), "toc": b.toc} if b else None


def delete_book(book_id: str) -> None:
    with db.session_scope() as s:
        s.execute(delete(Chunk).where(Chunk.book_id == book_id))
        s.execute(delete(Book).where(Book.id == book_id))
    book_path(book_id).unlink(missing_ok=True)


def retry_book(book_id: str) -> None:
    _set(book_id, status="queued", progress=0.0, error="")
