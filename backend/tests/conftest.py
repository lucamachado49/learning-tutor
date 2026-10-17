"""Fixtures: banco SQLite em memória e LLM falso (sem rede, sem GPU)."""

import pytest

import db
import llm
from models import Base


@pytest.fixture(autouse=True)
def memory_db():
    engine = db.init_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


class FakeProvider(llm.LLMProvider):
    def __init__(self, name, tokens=None, error=None, fail_after=None, configured=True):
        self.name, self.label = name, name
        self._tokens = tokens or []
        self._error = error
        self._fail_after = fail_after
        self._configured = configured
        self.calls = 0

    def configured(self):
        return self._configured

    async def stream(self, messages, temperature):
        self.calls += 1
        if self._error and self._fail_after is None:
            raise self._error
        for i, tok in enumerate(self._tokens):
            if self._fail_after is not None and i == self._fail_after:
                raise self._error
            yield tok


@pytest.fixture
def fake_llm(monkeypatch):
    """Substitui os provedores reais; devolve uma função para configurá-los."""
    def install(*providers, order=None):
        monkeypatch.setattr(llm, "PROVIDERS", {p.name: p for p in providers})
        monkeypatch.setattr(llm.config, "LLM_ORDER", order or [p.name for p in providers])
    return install
