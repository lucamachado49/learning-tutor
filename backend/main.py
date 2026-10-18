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
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

import config
import db
import library
import reranker
import llm
import tts
import verifier
import drills
import pronunciation
from domains import ACTIONS, DEFAULT_DOMAIN, DOMAINS, MODES, get_domain
from logging_setup import setup_logging

setup_logging()
log = logging.getLogger("tutor")

import cuda_setup  # noqa: F401  (registra DLLs do CUDA antes do faster_whisper)

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
_whisper_lock = threading.Lock()


def _get_whisper() -> Optional["WhisperModel"]:
    global _whisper_model
    if _whisper_model is not None or not WHISPER_AVAILABLE:
        return _whisper_model

    import numpy as np

    with _whisper_lock:  # aquecimento e requisições podem chegar juntos
        if _whisper_model is not None:
            return _whisper_model
        for device, ctype, size in [
            ("cuda", "float16", config.WHISPER_MODEL_GPU),
            ("cpu", "int8", config.WHISPER_MODEL_CPU),
        ]:
            try:
                model = WhisperModel(size, device=device, compute_type=ctype)
                # A GPU pode "carregar" e só falhar na inferência (ex.: DLL do cuBLAS ausente);
                # uma inferência curta valida o dispositivo e já aquece os kernels.
                list(model.transcribe(np.zeros(16000, dtype=np.float32), language="en")[0])
                _whisper_model = model
                log.info(f"Whisper pronto: {size} device={device}, compute={ctype}")
                return _whisper_model
            except Exception as exc:
                log.warning(f"Whisper ({device}) falhou: {exc}")

    log.error("Não foi possível carregar o Whisper.")
    return None


def _warm_whisper() -> None:
    _get_whisper()          # carrega, valida o dispositivo e aquece
    pronunciation.warm()    # modelo de fonemas (avaliação de pronúncia)
    reranker.warm()         # cross-encoder da busca na biblioteca


# ---------------------------------------------------------------------------
# Parse da resposta do LLM
# ---------------------------------------------------------------------------
_MSG_TAG = r"ME[NS]S?A(?:GEM|JE|GE)"
_SECTION = r"\[{}\]\s*(.*?)(?=\[(?:ME[NS]S?A(?:GEM|JE|GE)|FEEDBACK[^\]]*|ERROS|DOM[IÍ]NIO|VERIFICA[CÇ][AÃ]O|REVIS[AÃ]O)\]|$)"


def _section(name: str, text: str) -> Optional[str]:
    m = re.search(_SECTION.format(name), text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _parse_response(full_text: str) -> tuple[str, str, list[str]]:
    """Extrai [MENSAGEM], [FEEDBACK PEDAGÓGICO] e a lista de [ERROS]."""
    message = _section(_MSG_TAG, full_text)
    feedback = _section(r"FEEDBACK[^]]*", full_text) or ""
    errors_txt = _section("ERROS", full_text) or ""
    if message is None:
        message = re.split(r"\[(?:FEEDBACK|ERROS|DOM[IÍ]NIO|VERIFICA|REVIS)", full_text, flags=re.IGNORECASE)[0].strip()
    if not message and feedback:
        # O modelo pulou a [MENSAGEM] e escreveu tudo no feedback: mostra o feedback como resposta
        message, feedback = feedback, ""

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
        if m and m.group(1).lower() not in {"nenhum", "none"} and not m.group(1).startswith("<"):
            scores.append((m.group(1).strip()[:200], float(m.group(2))))
    return scores


# Citações como [3], [2, 6] ou [1-3]
_REVIEW_LINE = re.compile(r"^\s*[-•*]?\s*R(\d{1,2})\s*[:=–-]\s*(acertou|dif[ií]cil|errou)", re.IGNORECASE)
_REVIEW_QUALITY = {"acertou": 2, "difícil": 1, "dificil": 1, "errou": 0}


def _parse_review(full_text: str) -> dict[int, int]:
    """[REVISAO] → {número do item (1..n): qualidade}."""
    block = _section("REVIS[AÃ]O", full_text) or ""
    out = {}
    for line in block.splitlines():
        m = _REVIEW_LINE.match(line)
        if m:
            out[int(m.group(1))] = _REVIEW_QUALITY[m.group(2).lower()]
    return out


_JUDGE_PROMPT = """Você avalia uma sessão de revisão de um aluno. Abaixo estão os ITENS que estão
sendo revisados (erros que ele costumava cometer ou conceitos fracos) e a MENSAGEM do aluno.
Para cada item, decida se a mensagem mostra esse ponto:
- "acertou": usou/explicou corretamente
- "dificil": acertou em parte ou com hesitação
- "errou": cometeu o erro de novo
- "ausente": a mensagem não envolve esse item
Responda SOMENTE com JSON, ex.: {"R1": "errou", "R2": "ausente"}"""

_JUDGE_QUALITY = {"acertou": 2, "dificil": 1, "difícil": 1, "errou": 0}


async def _judge_review(items: list[dict], student_msg: str, req: "ChatRequest") -> dict[int, int]:
    """Avalia os itens pendentes numa chamada curta e separada (mais confiável que a seção oculta)."""
    listing = "\n".join(f"R{i}: {it['label']}" for i, it in enumerate(items, 1))
    try:
        raw = await llm.complete(
            [{"role": "system", "content": _JUDGE_PROMPT},
             {"role": "user", "content": f"ITENS:\n{listing}\n\nMENSAGEM DO ALUNO:\n{student_msg}"}],
            req.provider, req.ollama_model, fast=True,
        )
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception as exc:
        log.warning("Avaliação da revisão falhou: %s", exc)
        return {}
    out = {}
    for key, verdict in data.items():
        m = re.match(r"R(\d+)$", str(key).strip())
        q = _JUDGE_QUALITY.get(str(verdict).strip().lower())
        if m and q is not None:
            out[int(m.group(1))] = q
    return out


_CITATION_RE = re.compile(r"\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)\]")


def _cited_numbers(text: str) -> set[int]:
    nums: set[int] = set()
    for group in _CITATION_RE.findall(text):
        for part in group.split(","):
            bounds = [int(n) for n in re.split(r"\s*[–-]\s*", part.strip())]
            nums.update(range(bounds[0], bounds[-1] + 1) if len(bounds) == 2 else bounds)
    return nums


def _plain(text: str) -> str:
    """Texto legível para pré-visualização (remove HTML e marcações de markdown)."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_#`]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _used_citations(text: str, refs: list[dict]) -> list[dict]:
    """Referências citadas como [n] na resposta (ou todas, se o modelo não citou nenhuma)."""
    cited = _cited_numbers(text)
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
    # Turno de conversa por voz: prioriza latência
    fast:         bool = False


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    db.init_engine()
    # Carrega e aquece o Whisper em segundo plano (a 1ª inferência na GPU compila kernels)
    asyncio.create_task(asyncio.to_thread(_warm_whisper))
    worker = asyncio.create_task(library.worker_loop())
    yield
    worker.cancel()


def _run_migrations() -> None:
    """Aplica migrações pendentes do Alembic (idempotente)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent / "alembic.ini"))
    url = config.DATABASE_URL
    if url.startswith("postgresql") and "connect_timeout" not in url:
        # Sem timeout, o startup trava em silêncio se o Postgres estiver fora do ar
        url += ("&" if "?" in url else "?") + "connect_timeout=10"
    cfg.set_main_option("sqlalchemy.url", url)
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
        "gemini": {"available": llm.PROVIDERS["gemini"].configured() and not llm.in_cooldown("gemini"),
                   "model": config.GEMINI_MODEL, "cooldown": llm.in_cooldown("gemini")},
        "groq":   {"available": llm.PROVIDERS["groq"].configured() and not llm.in_cooldown("groq"),
                   "model": config.GROQ_MODEL, "cooldown": llm.in_cooldown("groq")},
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
        "pronunciation": pronunciation.available(),
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
    # Recusa calibrada: nenhum trecho relevante → o tutor diz que não está nos livros
    off_topic = bool(book_ids) and not action and references and not library.is_relevant(references)
    if off_topic:
        references = []
    outline = library.toc_outline(book_ids) if action == "roadmap" and book_ids else ""

    if action == "review":
        db.update_session(req.session_id, review_ids=db.due_review_ids(domain.id))
        session = db.get_session(req.session_id)
    review_items = db.review_items_by_ids(session.get("review_ids") or [])

    system = domain.system_prompt(level, mode, memory, mastery, references, outline, action)
    if review_items:
        lines = "\n".join(f"R{i}: [{it['kind']}] {it['label']}" for i, it in enumerate(review_items, 1))
        system += (
            "\n\nSESSÃO DE REVISÃO EM ANDAMENTO — itens pendentes (revise na ordem):\n" + lines +
            "\nQuando o aluno RESPONDER sobre um item, avalie-o adicionando AO FINAL a seção oculta:\n"
            "[REVISAO]\n- R<n>: acertou | difícil | errou\n"
            "OBRIGATÓRIO: sempre que a resposta do aluno mostrar (certo ou errado) algum desses "
            "itens — mesmo de passagem —, inclua a seção [REVISAO] com a avaliação. Avalie só "
            "itens que aparecem nesta mensagem do aluno. Quando todos forem avaliados, "
            "parabenize e encerre a revisão."
        )
    elif action == "review":
        system += "\n\nNão há itens para revisar hoje: diga isso e sugira um exercício ou conversa."
    answer_key = db.last_answer_key(req.session_id) if not action else ""
    if answer_key:
        system += (
            "\n\nGABARITO DO EXERCÍCIO ANTERIOR (calculado pelo SymPy — é a verdade, confie nele "
            "mais do que nas suas próprias contas):\n" + answer_key + "\n"
            "Compare a resposta do aluno com o gabarito. Se divergir, a resposta está ERRADA: "
            "aponte exatamente onde está o erro, sem elogiar o resultado incorreto."
        )
    if off_topic:
        system += (
            "\n\nOs livros do aluno NÃO têm trechos relevantes para esta pergunta. Comece a "
            "[MENSAGEM] dizendo isso claramente (\"Isso não está nos seus livros\"); depois, se "
            "fizer sentido, responda com conhecimento geral deixando explícito que não vem das fontes."
        )
    if req.fast and not action:
        system += (
            "\n\nCONVERSA POR VOZ: o aluno está falando com você em tempo real. A [MENSAGEM] deve "
            "ser curta e natural como numa conversa (2 a 3 frases, sem listas nem markdown), "
            "terminando com uma pergunta. Detalhes ficam no [FEEDBACK PEDAGÓGICO]."
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
            # Revisão: perguntas curtas, latência importa mais que raciocínio longo
            fast = (req.fast and not action) or action == "review" or bool(review_items)
            async for ev in llm.stream_chat(api_messages, req.provider, req.ollama_model, fast=fast):
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
            graded = _parse_review(full_text)
            if review_items and not graded and action != "review":
                graded = await _judge_review(review_items, req.message, req)
            if graded and review_items:
                done = set()
                for n, quality in graded.items():
                    if 1 <= n <= len(review_items):
                        db.grade_review(review_items[n - 1]["id"], quality)
                        done.add(review_items[n - 1]["id"])
                remaining = [it["id"] for it in review_items if it["id"] not in done]
                db.update_session(req.session_id, review_ids=remaining)

            final = {
                "token": "", "done": True, "provider": provider,
                "message": message, "feedback": feedback, "message_id": asst_id,
                "citations": citations, "verified": bool(new_key),
            }
            yield f"data: {json.dumps(final)}\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            # Cliente desconectou (ex.: aluno interrompeu por voz): guarda o que foi dito.
            # GeneratorExit: o gerador estava parado num yield quando foi fechado.
            if full_text.strip():
                message, feedback, _ = _parse_response(full_text)
                db.add_message(req.session_id, "assistant", message + " …(interrompido)", feedback, provider)
            raise
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


# ---------------------------------------------------------------------------
# Revisão espaçada e progresso
# ---------------------------------------------------------------------------
class ReviewGrade(BaseModel):
    quality: int  # 0 errou · 1 difícil · 2 acertou


@app.get("/api/review/today")
def review_today(domain: str = DEFAULT_DOMAIN):
    return db.review_today(get_domain(domain).id)


@app.post("/api/review/{item_id}/grade")
def review_grade(item_id: str, body: ReviewGrade):
    if body.quality not in (0, 1, 2):
        raise HTTPException(status_code=400, detail="quality deve ser 0, 1 ou 2.")
    if not db.grade_review(item_id, body.quality):
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return {"ok": True}


@app.get("/api/progress")
def progress(domain: str = DEFAULT_DOMAIN, days: int = 30):
    return db.review_progress(get_domain(domain).id, max(7, min(days, 180)))


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


@app.get("/api/books/{book_id}/file")
def book_file(book_id: str):
    """O PDF original, para o visualizador (abre na página citada)."""
    if not library.get_book(book_id):
        raise HTTPException(status_code=404, detail="Livro não encontrado.")
    path = library.book_path(book_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo do livro não encontrado.")
    return FileResponse(path, media_type="application/pdf")


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


# ---------------------------------------------------------------------------
# Pronúncia
# ---------------------------------------------------------------------------
@app.get("/api/pronunciation/drills")
def pronunciation_drills(language: str = DEFAULT_DOMAIN):
    return drills.drills_for(get_domain(language).speech_lang)


@app.post("/api/pronunciation")
async def assess_pronunciation(
    audio: UploadFile = File(...),
    reference: str = Form(...),
    language: str = Form(DEFAULT_DOMAIN),
):
    """Compara a gravação com a frase de referência, som a som."""
    if not pronunciation.available():
        raise HTTPException(status_code=503, detail="Avaliação de pronúncia indisponível (instale torch e transformers).")
    domain = get_domain(language)
    if domain.speech_lang not in pronunciation.ESPEAK_LANG:
        raise HTTPException(status_code=400, detail="Avaliação de pronúncia disponível para inglês e espanhol.")
    if len(reference) > 400:
        raise HTTPException(status_code=400, detail="Frase de referência longa demais (máx. 400 caracteres).")

    data = await audio.read()
    suffix = Path(audio.filename or "a.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    def _run() -> dict:
        from faster_whisper import decode_audio
        samples = decode_audio(str(tmp_path), sampling_rate=16000)
        if len(samples) < 16000 * 0.3:
            raise ValueError("Gravação curta demais.")
        return pronunciation.assess(samples, reference, domain.speech_lang)

    try:
        result = await asyncio.to_thread(_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Avaliação de pronúncia falhou")
        raise HTTPException(status_code=500, detail=f"Avaliação falhou: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    # Sons difíceis entram no mapa de domínio (acertou → 100, errou → 0)
    tips = pronunciation.TIPS_EN if domain.speech_lang == "en" else pronunciation.TIPS_ES
    assessed = {p["expected"] for w in result["words"] for p in w["phones"]} & set(tips)
    weak = set(result["weak_sounds"])
    if assessed:
        db.record_mastery(domain.id, [(f"pronúncia /{s}/", 0.0 if s in weak else 100.0) for s in sorted(assessed)])
        for s in sorted(assessed):
            db.grade_review_by_label(domain.id, f"pronúncia /{s}/", 0 if s in weak else 2)
    return result


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
