"""
config.py — Configuração central lida do arquivo .env na raiz do projeto.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR    = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
MODELS_DIR  = ROOT_DIR / "models"

load_dotenv(ROOT_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# --- LLM ---------------------------------------------------------------
# Ordem de tentativa no modo "auto"; provedores sem chave são pulados.
LLM_ORDER = [p.strip() for p in _env("LLM_ORDER", "gemini,groq,ollama").split(",") if p.strip()]
LLM_TEMPERATURE = float(_env("LLM_TEMPERATURE", "0.6"))
# Conversa por voz: latência importa mais (Groq responde em ~0,3 s)
VOICE_LLM_ORDER = [p.strip() for p in _env("VOICE_LLM_ORDER", "groq,gemini,ollama").split(",") if p.strip()]

GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL   = _env("GEMINI_MODEL", "gemini-flash-latest")  # alias: sempre o Flash atual

GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL   = _env("GROQ_MODEL", "openai/gpt-oss-120b")   # llama-3.3 saiu do catálogo do Groq

OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434")  # localhost tenta IPv6 antes (~2 s no Windows)
OLLAMA_MODEL    = _env("OLLAMA_MODEL", "qwen2.5:7b")

# Quantas mensagens anteriores enviar ao LLM (limita contexto/latência)
HISTORY_LIMIT = int(_env("HISTORY_LIMIT", "20"))

# --- STT ---------------------------------------------------------------
WHISPER_MODEL_GPU = _env("WHISPER_MODEL_GPU", "large-v3-turbo")  # ~0,4 s por frase numa RTX 4050
WHISPER_MODEL_CPU = _env("WHISPER_MODEL_CPU", "base")

# --- TTS ---------------------------------------------------------------
TTS_ORDER    = [p.strip() for p in _env("TTS_ORDER", "kokoro,piper").split(",") if p.strip()]
KOKORO_DIR   = MODELS_DIR / "kokoro"
KOKORO_MODEL = KOKORO_DIR / _env("KOKORO_MODEL_FILE", "kokoro-v1.0.onnx")
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
PIPER_DIR    = MODELS_DIR / "piper"

# --- Banco -------------------------------------------------------------
DATABASE_URL = _env("DATABASE_URL", "postgresql+psycopg://tutor:tutor@127.0.0.1:5434/tutor")

# --- Biblioteca (RAG) ---------------------------------------------------
BOOKS_DIR   = Path(_env("BOOKS_DIR", str(ROOT_DIR / "data" / "books")))
EMBED_MODEL = _env("EMBED_MODEL", "bge-m3")       # via Ollama
EMBED_DIM   = 1024                                # dimensão do bge-m3 (fixa no esquema)
RAG_TOP_K   = int(_env("RAG_TOP_K", "6"))
CHUNK_CHARS = int(_env("CHUNK_CHARS", "1500"))
# Reranker (cross-encoder): reordena os candidatos da busca híbrida
RERANK_ENABLED   = _env("RERANK_ENABLED", "1") == "1"
RERANK_MODEL     = _env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_CANDIDATES = int(_env("RERANK_CANDIDATES", "30"))
# Recusa calibrada: similaridade bge-m3 mínima do melhor trecho (abaixo: "não está nos livros")
RELEVANCE_MIN_SIM = float(_env("RELEVANCE_MIN_SIM", "0.46"))

# --- Logs --------------------------------------------------------------
LOG_LEVEL  = _env("LOG_LEVEL", "INFO")
LOG_FORMAT = _env("LOG_FORMAT", "text")   # "text" ou "json"
