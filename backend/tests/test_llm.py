import pytest

import llm
from conftest import FakeProvider


async def _collect(**kw):
    return [ev async for ev in llm.stream_chat([{"role": "user", "content": "oi"}], **kw)]


async def test_fallback_skips_unconfigured_and_failing(fake_llm):
    a = FakeProvider("a", configured=False)
    b = FakeProvider("b", error=llm.ProviderUnavailable("cota esgotada"))
    c = FakeProvider("c", tokens=["Olá", "!"])
    fake_llm(a, b, c)

    events = await _collect()
    assert "".join(e.token for e in events) == "Olá!"
    assert {e.provider for e in events} == {"c"}
    assert a.calls == 0 and b.calls == 1


async def test_failure_mid_stream_does_not_switch_provider(fake_llm):
    a = FakeProvider("a", tokens=["um", "dois"], error=RuntimeError("caiu"), fail_after=1)
    b = FakeProvider("b", tokens=["nunca"])
    fake_llm(a, b)

    events = await _collect()
    assert events[0].token == "um"
    assert "ERRO" in events[-1].token
    assert b.calls == 0


async def test_all_unavailable_raises(fake_llm):
    fake_llm(FakeProvider("a", configured=False))
    with pytest.raises(llm.ProviderUnavailable):
        await _collect()


async def test_explicit_provider_ignores_order(fake_llm):
    a = FakeProvider("a", tokens=["A"])
    b = FakeProvider("b", tokens=["B"])
    fake_llm(a, b)
    events = await _collect(provider="b")
    assert [e.token for e in events] == ["B"]


async def test_fast_mode_uses_voice_order(fake_llm, monkeypatch):
    a = FakeProvider("a", tokens=["lento"])
    b = FakeProvider("b", tokens=["rápido"])
    fake_llm(a, b, order=["a", "b"])
    monkeypatch.setattr(llm.config, "VOICE_LLM_ORDER", ["b", "a"])
    assert [e.token for e in await _collect(fast=True)] == ["rápido"]
    assert [e.token for e in await _collect()] == ["lento"]
