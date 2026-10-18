"""
reranker.py — Reordena candidatos da busca híbrida com um cross-encoder.

A busca híbrida (vetor + BM25 + RRF) é boa para achar candidatos, mas compara pergunta e
trecho separadamente. O cross-encoder lê os dois JUNTOS e dá uma nota de relevância mais
precisa — é a etapa de maior ganho no RAG. Modelo: BAAI/bge-reranker-v2-m3 (multilíngue,
pergunta em português × livro em inglês funciona).

Sem PyTorch (ou se o modelo falhar), a ordem da busca híbrida é mantida.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import config

log = logging.getLogger("tutor.reranker")

_model = None
_tokenizer = None
_device = "cpu"
_lock = threading.Lock()
_failed = False


def available() -> bool:
    if not config.RERANK_ENABLED or _failed:
        return False
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _load() -> bool:
    global _model, _tokenizer, _device, _failed
    if _model is not None:
        return True
    with _lock:
        if _model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            _device = "cuda" if torch.cuda.is_available() else "cpu"
            _tokenizer = AutoTokenizer.from_pretrained(config.RERANK_MODEL)
            model = AutoModelForSequenceClassification.from_pretrained(config.RERANK_MODEL)
            if _device == "cuda":
                model = model.half()
            _model = model.to(_device).eval()
            log.info("Reranker pronto: %s (%s)", config.RERANK_MODEL, _device)
            return True
        except Exception as exc:
            _failed = True
            log.warning("Reranker indisponível, usando a ordem da busca híbrida: %s", exc)
            return False


def warm() -> None:
    if available() and _load():
        rerank("teste", [{"content": "teste"}], 1)


def scores(query: str, passages: list[str], batch: int = 16) -> list[float]:
    import torch

    out: list[float] = []
    for i in range(0, len(passages), batch):
        pairs = [[query, p] for p in passages[i:i + batch]]
        enc = _tokenizer(pairs, padding=True, truncation=True, max_length=384, return_tensors="pt").to(_device)
        with torch.inference_mode():
            logits = _model(**enc).logits.view(-1).float()
        out.extend(logits.cpu().tolist())
    return out


def rerank(query: str, candidates: list[dict], k: int, text_key: str = "content") -> list[dict]:
    """Devolve os k candidatos mais relevantes (com 'rerank_score'); sem modelo, os k primeiros."""
    if not candidates:
        return []
    if not available() or not _load():
        return candidates[:k]
    try:
        texts = [f"{c.get('section', '')}\n{c[text_key]}" for c in candidates]
        for c, s in zip(candidates, scores(query, texts)):
            c["rerank_score"] = s
        return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)[:k]
    except Exception as exc:
        log.warning("Reranking falhou, mantendo a ordem híbrida: %s", exc)
        return candidates[:k]

