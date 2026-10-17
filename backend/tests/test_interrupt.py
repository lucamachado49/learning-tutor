"""Interrupção (barge-in): a parte da resposta já gerada deve ficar no histórico."""

import asyncio
import json

import db
import llm
import main
from conftest import FakeProvider


class SlowProvider(FakeProvider):
    async def stream(self, messages, temperature, fast=False):
        for tok in ["[MENSAGEM]\n", "Once upon ", "a time ", "there was ", "a dragon"]:
            await asyncio.sleep(0.01)
            yield tok


async def test_partial_reply_saved_when_client_disconnects(fake_llm):
    fake_llm(SlowProvider("slow"))
    sid = db.create_session("en", "B1", "conversation")["id"]
    resp = await main.chat_stream(main.ChatRequest(session_id=sid, message="Tell me a story", fast=True))

    gen = resp.body_iterator
    received = [json.loads((await gen.__anext__())[6:])["token"] for _ in range(3)]
    await gen.aclose()  # cliente desconectou no meio da resposta

    msgs = db.get_messages(sid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"].startswith("Once upon a time")
    assert msgs[1]["content"].endswith("(interrompido)")
    assert "".join(received).startswith("[MENSAGEM]")
