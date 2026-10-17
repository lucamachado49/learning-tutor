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
import llm
import tts
from domains import DEFAULT_DOMAIN, DOMAINS, MODES, get_domain

logging.basicConfig(level=logging.INFO)
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
_SECTION = r"\[{}\]\s*(.*?)(?=\[(?:MENSAGEM|FEEDBACK PEDAG[ÓO]GICO|ERROS)\]|$)"


def _section(name: str, text: str) -> Optional[str]:
    m = re.search(_SECTION.format(name), text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _parse_response(full_text: str) -> tuple[str, str, list[str]]:
    """Extrai [MENSAGEM], [FEEDBACK PEDAGÓGICO] e a lista de [ERROS]."""
    message = _section("MENSAGEM", full_text)
    feedback = _section("FEEDBACK PEDAG[ÓO]GICO", full_text) or ""
    errors_txt = _section("ERROS", full_text) or ""
    if message is None:
        message = re.split(r"\[(?:FEEDBACK|ERROS)", full_text, flags=re.IGNORECASE)[0].strip()

    errors = []
    for line in errors_txt.splitlines():
        line = line.strip()
        if not line.startswith(("-", "•", "*")):
            continue  # ignora comentários soltos do modelo
        item = line.lstrip("-•* ").strip()
        if item and item.lower().rstrip(".") not in {"nenhum", "nenhuma", "none"}:
            errors.append(item[:300])
    return message, feedback, errors


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------
class SessionCreate(BaseModel):
    domain: str = DEFAULT_DOMAIN
    level:  Optional[str] = None
    mode:   str = "conversation"


class ChatRequest(BaseModel):
    session_id:   str
    message:      str
    domain:       Optional[str] = None
    level:        Optional[str] = None
    mode:         Optional[str] = None
    provider:     str = "auto"
    ollama_model: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _get_whisper()
    yield


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
    }


@app.get("/api/domains")
async def list_domains():
    return {
        "domains": [d.public() for d in DOMAINS.values()],
        "modes": MODES,
        "default": DEFAULT_DOMAIN,
    }


@app.get("/api/sessions")
async def list_sessions():
    return db.list_sessions()


@app.post("/api/sessions", status_code=201)
async def create_session(body: SessionCreate):
    domain = get_domain(body.domain)
    level = body.level if body.level in domain.levels else domain.default_level
    mode = body.mode if body.mode in MODES else "conversation"
    return db.create_session(domain.id, level, mode)


@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    return db.get_messages(session_id)


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
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
    domain = get_domain(req.domain or session.get("domain") or session["language"])
    level = req.level if req.level in domain.levels else (
        session["level"] if session["level"] in domain.levels else domain.default_level
    )
    mode = req.mode if req.mode in MODES else session.get("mode") or "conversation"

    history = db.get_messages(req.session_id, limit=config.HISTORY_LIMIT)
    db.add_message(req.session_id, "user", req.message)
    updates = {"domain": domain.id, "language": domain.id, "level": level, "mode": mode}
    if not history:
        updates["title"] = req.message[:55] + ("…" if len(req.message) > 55 else "")
    db.update_session(req.session_id, **updates)

    memory = [m["text"] for m in db.top_mistakes(domain.id)]
    api_messages = [{"role": "system", "content": domain.system_prompt(level, mode, memory)}]
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
            asst_id = db.add_message(req.session_id, "assistant", message, feedback)
            db.update_session(req.session_id)
            if errors:
                db.record_mistakes(domain.id, errors)

            final = {
                "token": "", "done": True, "provider": provider,
                "message": message, "feedback": feedback, "message_id": asst_id,
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


@app.get("/api/memory/{domain_id}")
async def get_memory(domain_id: str):
    return db.top_mistakes(domain_id, limit=50)


@app.delete("/api/memory/item/{mistake_id}")
async def delete_memory_item(mistake_id: str):
    db.delete_mistake(mistake_id)
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
