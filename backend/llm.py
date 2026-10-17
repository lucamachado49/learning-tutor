"""
llm.py — Provedores de LLM plugáveis com fallback automático.

Todos recebem mensagens no formato OpenAI ({"role", "content"}) e geram
tokens em streaming. No modo "auto", se um provedor falhar ANTES de emitir
o primeiro token (sem chave, limite de cota, offline), o próximo é tentado.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import httpx

import config

log = logging.getLogger("tutor.llm")


class ProviderUnavailable(Exception):
    """Provedor não pôde atender (sem chave, offline, cota esgotada)."""


@dataclass
class StreamEvent:
    provider: str
    token: str


class LLMProvider:
    name: str = ""
    label: str = ""

    def configured(self) -> bool:
        return True

    def model_name(self) -> str:
        return ""

    async def stream(
        self, messages: list[dict], temperature: float, fast: bool = False,
    ) -> AsyncGenerator[str, None]:
        """fast=True: prioriza latência (ex.: conversa por voz) em vez de raciocínio longo."""
        raise NotImplementedError
        yield  # pragma: no cover


def _raise_for_status(resp: httpx.Response, provider: str, body: bytes) -> None:
    if resp.status_code >= 400:
        detail = body.decode(errors="ignore")[:300]
        raise ProviderUnavailable(f"{provider} HTTP {resp.status_code}: {detail}")


# ---------------------------------------------------------------------------
# Gemini (Google AI Studio — nível gratuito)
# ---------------------------------------------------------------------------
class GeminiProvider(LLMProvider):
    name, label = "gemini", "Google Gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"

    def configured(self) -> bool:
        return bool(config.GEMINI_API_KEY)

    def model_name(self) -> str:
        return config.GEMINI_MODEL

    async def stream(self, messages, temperature, fast=False):
        try:
            async for token in self._stream(messages, temperature, fast):
                yield token
        except ProviderUnavailable as exc:
            # Nem todo modelo aceita desligar o raciocínio: tenta de novo no modo normal
            if fast and "HTTP 400" in str(exc):
                async for token in self._stream(messages, temperature, False):
                    yield token
            else:
                raise

    async def _stream(self, messages, temperature, fast):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ]
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if fast:
            # Sem "pensar" antes de responder: 1º token ~2x mais rápido
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        url = self.URL.format(model=config.GEMINI_MODEL)
        headers = {"x-goog-api-key": config.GEMINI_API_KEY}
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    _raise_for_status(resp, self.label, await resp.aread())
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = json.loads(line[5:].strip())
                    for cand in data.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            if part.get("text"):
                                yield part["text"]


# ---------------------------------------------------------------------------
# Groq (API compatível com OpenAI — nível gratuito)
# ---------------------------------------------------------------------------
class GroqProvider(LLMProvider):
    name, label = "groq", "Groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def configured(self) -> bool:
        return bool(config.GROQ_API_KEY)

    def model_name(self) -> str:
        return config.GROQ_MODEL

    async def stream(self, messages, temperature, fast=False):
        payload = {
            "model": config.GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", self.URL, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    _raise_for_status(resp, self.label, await resp.aread())
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    delta = json.loads(raw)["choices"][0].get("delta", {})
                    if delta.get("content"):
                        yield delta["content"]


# ---------------------------------------------------------------------------
# Ollama (local / offline)
# ---------------------------------------------------------------------------
class OllamaProvider(LLMProvider):
    name, label = "ollama", "Ollama (local)"

    def __init__(self) -> None:
        self.model: str = config.OLLAMA_MODEL

    def model_name(self) -> str:
        return self.model

    async def list_models(self) -> Optional[list[str]]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return None

    async def stream(self, messages, temperature, fast=False):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", f"{config.OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                    if resp.status_code >= 400:
                        _raise_for_status(resp, self.label, await resp.aread())
                    async for raw in resp.aiter_lines():
                        if not raw.strip():
                            continue
                        data = json.loads(raw)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
        except httpx.ConnectError as exc:
            raise ProviderUnavailable("Ollama offline (execute: ollama serve)") from exc


PROVIDERS: dict[str, LLMProvider] = {
    p.name: p for p in (GeminiProvider(), GroqProvider(), OllamaProvider())
}


async def stream_chat(
    messages: list[dict],
    provider: str = "auto",
    ollama_model: Optional[str] = None,
    temperature: float = config.LLM_TEMPERATURE,
    fast: bool = False,
) -> AsyncGenerator[StreamEvent, None]:
    """Faz streaming com o provedor pedido ou, em "auto", com fallback em ordem.

    fast=True (conversa por voz) usa a ordem VOICE_LLM_ORDER e desliga o raciocínio longo.
    """
    if ollama_model:
        PROVIDERS["ollama"].model = ollama_model  # type: ignore[attr-defined]

    if provider != "auto":
        order = [provider]
    else:
        order = config.VOICE_LLM_ORDER if fast else config.LLM_ORDER
    errors: list[str] = []

    for name in order:
        prov = PROVIDERS.get(name)
        if prov is None:
            continue
        if not prov.configured():
            errors.append(f"{prov.label}: sem chave no .env")
            continue

        started = False
        try:
            async for token in prov.stream(messages, temperature, fast):
                started = True
                yield StreamEvent(prov.name, token)
            if started:
                return
            errors.append(f"{prov.label}: resposta vazia")
        except Exception as exc:
            if started:
                # Falha no meio da resposta: não dá para trocar de provedor.
                yield StreamEvent(prov.name, f"\n\n[ERRO: {exc}]")
                return
            log.warning("LLM %s indisponível: %s", prov.name, exc)
            errors.append(f"{prov.label}: {exc}")

    raise ProviderUnavailable("Nenhum LLM disponível. " + " | ".join(errors))


async def complete(
    messages: list[dict],
    provider: str = "auto",
    ollama_model: Optional[str] = None,
    temperature: float = 0.1,
) -> str:
    """Resposta completa (sem streaming) — para tarefas auxiliares curtas."""
    parts = [ev.token async for ev in stream_chat(messages, provider, ollama_model, temperature)]
    return "".join(parts)
