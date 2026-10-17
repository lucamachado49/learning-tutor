"""
main.py — FastAPI Backend · AI Learning Tutor
==============================================
Endpoints:
  GET  /api/health                 → status dos provedores
  GET  /api/domains                → domínios, níveis e modos disponíveis
  GET  /api/sessions
  POST /api/sessions
  GET  /api/sessions/{id}/messages
  DEL  /api/sessions/{id}
  POST /api/chat/stream            → SSE token-by-token
  GET  /api/memory/{domain}        → erros/lacunas recorrentes do aluno
  DEL  /api/memory/item/{id}
  POST /api/transcribe             → multipart audio → JSON transcript
  POST /api/tts                    → form text → WAV
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import config
import db
import library
import llm
import tts
import verifier
from domains import ACTIONS, DEFAULT_DOMAIN, DOMAINS, MODES, get_domain
from logging_setup import setup_logging

setup_logging()
log = logging.getLogger("tutor")

try:
    from faster_whisper import WhisperModel  # type: ignore
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    log.warning("faster-whisper não instalado — STT desabilitado.")


# ---------------------------------------------------------------------------
# Whisper STT (singleton com lazy loading)
# ---------------------------------------------------------------------------
_whisper_model: Optional["WhisperModel"] = None


def _get_whisper() -> Optional["WhisperModel"]:
    global _whisper_model
    if _whisper_model is not None or not WHISPER_AVAILABLE:
        return _whisper_model

    for device, ctype, size in [
        ("cuda", "float16", config.WHISPER_MODEL_GPU),
        ("cpu", "int8", config.WHISPER_MODEL_CPU),
    ]:
        try:
            _whisper_model = WhisperModel(size, device=device, compute_type=ctype)
            log.info(f"Whisper carregado: {size} device={device}, compute={ctype}")
            return _whisper_model
        except Exception as exc:
            log.warning(f"Whisper ({device}) falhou: {exc}")

    log.error("Não foi possível carregar o Whisper.")
    return None


# ---------------------------------------------------------------------------
# Parse da resposta do LLM
# ---------------------------------------------------------------------------
_SECTION = r"\[{}\]\s*(.*?)(?=\[(?:MENSAGEM|FEEDBACK[^\]]*|ERROS|DOM[IÍ]NIO|VERIFICA[CÇ][AÃ]O)\]|$)"


def _section(name: str, text: str) -> Optional[str]:
    m = re.search(_SECTION.format(name), text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _parse_response(full_text: str) -> tuple[str, str, list[str]]:
    """Extrai [MENSAGEM], [FEEDBACK PEDAGÓGICO] e a lista de [ERROS]."""
    message = _section("MENSAGEM", full_text)
    feedback = _section(r"FEEDBACK[^]]*", full_text) or ""
    errors_txt = _section("ERROS", full_text) or ""
    if message is None:
        message = re.split(r"\[(?:FEEDBACK|ERROS|DOM[IÍ]NIO|VERIFICA)", full_text, flags=re.IGNORECASE)[0].strip()

    errors = []
    for line in errors_txt.splitlines():
        line = line.strip()
        if not line.startswith(("-", "•", "*")):
            continue  # ignora comentários soltos do modelo
        item = line.lstrip("-•* ").strip()
        if item and item.lower().rstrip(".") not in {"nenhum", "nenhuma", "none"}:
            errors.append(item[:300])
    return message, feedback, errors


def _parse_mastery(full_text: str) -> list[tuple[str, float]]:
    """Extrai '- conceito: nota' da seção [DOMINIO]."""
    block = _section("DOM[IÍ]NIO", full_text) or ""
    scores = []
    for line in block.splitlines():
        m = re.match(r"^\s*[-•*]\s*(.+?)\s*[:=]\s*(\d{1,3})(?:\s*/\s*100)?\s*$", line)
        if m and m.group(1).lower() not in {"nenhum", "none"}:
            scores.append((m.group(1).strip()[:200], float(m.group(2))))
    return scores


_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def _plain(text: str) -> str:
    """Texto legível para pré-visualização (remove HTML e marcações de markdown)."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_#`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _used_citations(text: str, refs: list[dict]) -> list[dict]:
    """Referências citadas como [n] na resposta (ou todas, se o modelo não citou nenhuma)."""
    cited = {int(n) for n in _CITATION_RE.findall(text)}
    out = []
    for i, r in enumerate(refs, 1):
        if (cited and i not in cited) or (not cited and i > 3):
            continue
        out.append({
            "n": i, "book_id": r["book_id"], "book": r["book"], "section": r["section"],
            "page_start": r["page_start"], "page_end": r["page_end"], "kind": r["kind"],
            "snippet": _plain(r["content"])[:400],
        })
    return out


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------
class SessionCreate(BaseModel):
    domain:   str = DEFAULT_DOMAIN
    level:    Optional[str] = None
    mode:     str = "conversation"
    book_ids: list[str] = []


class SessionBooks(BaseModel):
    book_ids: list[str]


class ChatRequest(BaseModel):
    session_id:   str
    message:      str
    domain:       Optional[str] = None
    level:        Optional[str] = None
    mode:         Optional[str] = None
    provider:     str = "auto"
    ollama_model: Optional[str] = None
    # Ação rápida da interface: roadmap | exercise | diagnosis
    action:       Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    db.init_engine()
    _get_whisper()
    worker = asyncio.create_task(library.worker_loop())
    yield
    worker.cancel()


def _run_migrations() -> None:
    """Aplica migrações pendentes do Alembic (idempotente)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
    command.upgrade(cfg, "head")
    setup_logging()  # o alembic reconfigura o logging ao rodar


app = FastAPI(title="Learning Tutor API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    ollama_models = await llm.PROVIDERS["ollama"].list_models()  # type: ignore[attr-defined]
    if ollama_models is not None:
        # Modelos de embeddings não conversam: ficam fora do seletor de LLM
        ollama_models = [m for m in ollama_models
                         if not m.startswith(config.EMBED_MODEL) and "embed" not in m]
    providers = {
        "gemini": {"available": llm.PROVIDERS["gemini"].configured(), "model": config.GEMINI_MODEL},
        "groq":   {"available": llm.PROVIDERS["groq"].configured(),   "model": config.GROQ_MODEL},
        "ollama": {"available": ollama_models is not None, "model": config.OLLAMA_MODEL},
    }
    return {
        "status": "ok",
        "llm_order": config.LLM_ORDER,
        "providers": providers,
        "llm": any(p["available"] for p in providers.values()),
        # compatibilidade com o frontend antigo
        "ollama": ollama_models is not None,
        "models": ollama_models or [],
        "whisper": WHISPER_AVAILABLE,
        "tts": tts.status(),
        "database": await asyncio.to_thread(db.ping),
    }


@app.get("/api/domains")
async def list_domains():
    return {
        "domains": [d.public() for d in DOMAINS.values()],
        "modes": MODES,
        "default": DEFAULT_DOMAIN,
    }


@app.get("/api/sessions")
def list_sessions():
    return db.list_sessions()


@app.post("/api/sessions", status_code=201)
def create_session(body: SessionCreate):
    domain = get_domain(body.domain)
    level = body.level if body.level in domain.levels else domain.default_level
    mode = body.mode if body.mode in MODES else "conversation"
    return db.create_session(domain.id, level, mode, body.book_ids)


@app.put("/api/sessions/{session_id}/books")
def set_session_books(session_id: str, body: SessionBooks):
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    db.update_session(session_id, book_ids=body.book_ids)
    return db.get_session(session_id)


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    return db.get_messages(session_id)


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    db.delete_session(session_id)
    return {"ok": True}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Streaming SSE da resposta do tutor.
    Envia: data: {"token": "...", "done": false, "provider": "..."}
    Final: data: {"done": true, "message": "...", "feedback": "...", "message_id": "...", "provider": "..."}
    """
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    # Idioma/nível/modo podem mudar no meio da sessão; persistimos o último usado.
    domain = get_domain(req.domain or session["domain"])
    level = req.level if req.level in domain.levels else (
        session["level"] if session["level"] in domain.levels else domain.default_level
    )
    mode = req.mode if req.mode in MODES else session.get("mode") or "conversation"

    history = db.get_messages(req.session_id, limit=config.HISTORY_LIMIT)
    db.add_message(req.session_id, "user", req.message)
    updates = {"domain": domain.id, "level": level, "mode": mode}
    if not history:
        updates["title"] = req.message[:55] + ("…" if len(req.message) > 55 else "")
    db.update_session(req.session_id, **updates)

    memory = [m["text"] for m in db.top_mistakes(domain.id)]
    mastery = db.get_mastery(domain.id, limit=15)
    action = req.action if req.action in ACTIONS else None

    # RAG: busca nos livros da sessão (a última fala do tutor ajuda a manter o contexto)
    references: list[dict] = []
    book_ids = session.get("book_ids") or []
    if book_ids:
        query = req.message
        if action == "exercise" and mastery:
            query += " " + " ".join(m["concept"] for m in mastery[:3])
        elif history and history[-1]["role"] == "assistant":
            query = history[-1]["content"][-500:] + "\n" + req.message
        try:
            kind = "exercise" if action == "exercise" else ""
            references = await asyncio.to_thread(library.search, query, book_ids, config.RAG_TOP_K, kind)
            if kind and not references:
                references = await asyncio.to_thread(library.search, query, book_ids)
        except Exception as exc:
            log.warning("Busca na biblioteca falhou: %s", exc)
    outline = library.toc_outline(book_ids) if action == "roadmap" and book_ids else ""

    system = domain.system_prompt(level, mode, memory, mastery, references, outline, action)
    answer_key = db.last_answer_key(req.session_id) if not action else ""
    if answer_key:
        system += (
            "\n\nGABARITO DO EXERCÍCIO ANTERIOR (calculado pelo SymPy — é a verdade, confie nele "
            "mais do que nas suas próprias contas):\n" + answer_key + "\n"
            "Compare a resposta do aluno com o gabarito. Se divergir, a resposta está ERRADA: "
            "aponte exatamente onde está o erro, sem elogiar o resultado incorreto."
        )
    api_messages = [{"role": "system", "content": system}]
    for row in history:
        content = row["content"]
        # Inclui o feedback anterior para o tutor lembrar das correções que fez
        if row["role"] == "assistant" and row.get("feedback"):
            content += f"\n\n[FEEDBACK PEDAGÓGICO]\n{row['feedback']}"
        api_messages.append({"role": row["role"], "content": content})
    api_messages.append({"role": "user", "content": req.message})

    async def _generate() -> AsyncGenerator[str, None]:
        full_text, provider = "", ""
        try:
            async for ev in llm.stream_chat(api_messages, req.provider, req.ollama_model):
                full_text += ev.token
                provider = ev.provider
                yield f"data: {json.dumps({'token': ev.token, 'done': False, 'provider': provider})}\n\n"

            message, feedback, errors = _parse_response(full_text)
            citations = _used_citations(message + feedback, references)
            new_key = ""
            if action == "exercise" and domain.kind == "tech":
                new_key = await _answer_key(full_text, message, req)
            asst_id = db.add_message(req.session_id, "assistant", message, feedback, provider,
                                     citations, new_key)
            db.update_session(req.session_id)
            if errors:
                db.record_mistakes(domain.id, errors)
            scores = _parse_mastery(full_text)
            if scores:
                db.record_mastery(domain.id, scores)

            final = {
                "token": "", "done": True, "provider": provider,
                "message": message, "feedback": feedback, "message_id": asst_id,
                "citations": citations, "verified": bool(new_key),
            }
            yield f"data: {json.dumps(final)}\n\n"

        except Exception as exc:
            log.exception("Erro no streaming")
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_SYMPY_PROMPT = """Você converte exercícios de matemática em código SymPy que CALCULA a resposta.
Responda SOMENTE com expressões SymPy, uma por linha, sem import, sem comentários, sem texto.
Use apenas: Matrix, symbols, Rational, sqrt, exp, log, sin, cos, diff, integrate, limit, solve,
simplify, expand, factor, hessian, gradient(f, [vars]), jacobian([fs], [vars]) e as variáveis
x, y, z, t, w (para mais variáveis: x1, x2, x3 = symbols("x1 x2 x3")). Atribuições simples são permitidas.
Exemplo para "autovalores de [[1,2],[3,4]]":
A = Matrix([[1, 2], [3, 4]])
A.eigenvals()
Se o exercício não tiver resposta calculável, responda apenas: NENHUM"""


def _strip_fences(code: str) -> str:
    return "\n".join(l for l in code.splitlines() if not l.strip().startswith("```"))


async def _answer_key(full_text: str, exercise: str, req: "ChatRequest") -> str:
    """Gabarito via SymPy: usa o bloco [VERIFICACAO] do tutor ou pede o código numa chamada focada."""
    code = _strip_fences(_section("VERIFICA[CÇ][AÃ]O", full_text) or "")
    key = await asyncio.to_thread(verifier.try_run, code) if code.strip() else ""
    if key:
        return key
    convo = [{"role": "system", "content": _SYMPY_PROMPT}, {"role": "user", "content": exercise}]
    for attempt in range(2):  # 1 tentativa + 1 autocorreção com o erro
        try:
            code = _strip_fences(await llm.complete(convo, req.provider, req.ollama_model))
        except Exception as exc:
            log.warning("Geração do código SymPy falhou: %s", exc)
            return ""
        if "NENHUM" in code.upper():
            return ""
        try:
            return await asyncio.to_thread(verifier.run, code)
        except Exception as exc:
            log.info("Código SymPy inválido (tentativa %d): %s", attempt + 1, exc)
            convo += [
                {"role": "assistant", "content": code},
                {"role": "user", "content": f"Erro: {exc}. Corrija e responda só com o código."},
            ]
    return ""


@app.get("/api/memory/{domain_id}")
def get_memory(domain_id: str):
    return db.top_mistakes(domain_id, limit=50)


@app.delete("/api/memory/item/{mistake_id}")
def delete_memory_item(mistake_id: str):
    db.delete_mistake(mistake_id)
    return {"ok": True}


@app.get("/api/mastery/{domain_id}")
def get_mastery(domain_id: str):
    return db.get_mastery(domain_id)


@app.delete("/api/mastery/item/{item_id}")
def delete_mastery_item(item_id: str):
    db.delete_mastery(item_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Biblioteca
# ---------------------------------------------------------------------------
MAX_BOOK_MB = 200


@app.post("/api/books", status_code=201)
async def upload_book(file: UploadFile = File(...), domain: str = Form("")):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF.")
    data = await file.read()
    if len(data) > MAX_BOOK_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"PDF maior que {MAX_BOOK_MB} MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Arquivo não parece ser um PDF válido.")
    return await asyncio.to_thread(library.create_book, file.filename, data, domain)


@app.get("/api/books")
def list_books():
    return library.list_books()


@app.get("/api/books/search")
def search_books(q: str, book_ids: str, k: int = 6):
    """Busca direta (útil para depuração): book_ids separados por vírgula."""
    return library.search(q, [b for b in book_ids.split(",") if b], k)


@app.get("/api/books/{book_id}")
def get_book(book_id: str):
    book = library.get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Livro não encontrado.")
    return book


@app.delete("/api/books/{book_id}")
def delete_book(book_id: str):
    library.delete_book(book_id)
    return {"ok": True}


@app.post("/api/books/{book_id}/retry")
def retry_book(book_id: str):
    library.retry_book(book_id)
    return {"ok": True}


@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form(DEFAULT_DOMAIN),
):
    """Transcreve áudio (WebM/WAV) com faster-whisper. `language` é o id do domínio."""
    if not WHISPER_AVAILABLE:
        raise HTTPException(status_code=503, detail="faster-whisper não instalado.")

    whisper = _get_whisper()
    if whisper is None:
        raise HTTPException(status_code=503, detail="Modelo Whisper não pôde ser carregado.")

    lang_code = get_domain(language).speech_lang
    audio_bytes = await audio.read()

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    def _run() -> str:
        segments, _ = whisper.transcribe(str(tmp_path), language=lang_code, beam_size=5, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()

    try:
        text = await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcrição falhou: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"transcript": text}


@app.post("/api/tts")
async def text_to_speech(
    text: str = Form(...),
    language: str = Form(DEFAULT_DOMAIN),
    speed: float = Form(1.0),
):
    """Sintetiza a [MENSAGEM] em WAV. `language` é o id do domínio."""
    lang = get_domain(language).speech_lang
    try:
        wav, engine = await asyncio.to_thread(tts.synthesize, text, lang, speed)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Síntese TTS falhou: {exc}")

    return Response(
        content=wav,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=speech.wav", "X-TTS-Engine": engine},
    )
