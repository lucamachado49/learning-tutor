"""Testes de API sem rodar o lifespan (não carrega Whisper nem migrações)."""

import json

import pytest
from fastapi.testclient import TestClient

import db
from conftest import FakeProvider
from main import app


@pytest.fixture
def client():
    return TestClient(app)  # sem "with": o lifespan não roda


def test_domains(client):
    data = client.get("/api/domains").json()
    ids = {d["id"] for d in data["domains"]}
    assert {"en", "es", "math_ml", "mle", "cto"} <= ids
    assert data["default"] == "en"


def test_create_session_normalizes_level(client):
    s = client.post("/api/sessions", json={"domain": "math_ml", "level": "B1"}).json()
    assert s["domain"] == "math_ml"
    assert s["level"] == "Intermediário"  # B1 não existe em domínio técnico


def test_chat_stream_persists_and_records_memory(client, fake_llm):
    reply = "[MENSAGEM]\nNice!\n[FEEDBACK PEDAGÓGICO]\nUse 'went'.\n[ERROS]\n- usa 'go' no passado"
    fake_llm(FakeProvider("fake", tokens=[reply[:20], reply[20:]]))

    sid = client.post("/api/sessions", json={"domain": "en"}).json()["id"]
    resp = client.post("/api/chat/stream", json={"session_id": sid, "message": "I go yesterday"})
    events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]

    final = events[-1]
    assert final["done"] and final["message"] == "Nice!" and final["provider"] == "fake"

    msgs = db.get_messages(sid)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["feedback"] == "Use 'went'."
    assert db.get_session(sid)["title"] == "I go yesterday"
    assert db.top_mistakes("en")[0]["text"] == "usa 'go' no passado"


def test_chat_unknown_session_404(client):
    r = client.post("/api/chat/stream", json={"session_id": "nope", "message": "oi"})
    assert r.status_code == 404


def test_review_session_grades_and_reschedules(client, fake_llm):
    import review as rv
    with db.session_scope() as s:
        for t in ["usa 'go' no passado", "esquece o 'the'"]:
            s.add(rv.Mistake(domain="en", text=t, norm=t, first_seen=rv.utcnow(), last_seen=rv.utcnow()))
    sid = client.post("/api/sessions", json={"domain": "en"}).json()["id"]

    # 1) Inicia a revisão: os 2 erros antigos viram itens vencidos e entram na sessão
    fake_llm(FakeProvider("fake", tokens=["[MENSAGEM]\nTranslate: 'Eu fui à praia ontem.'"]))
    client.post("/api/chat/stream", json={"session_id": sid, "message": "Revisar", "action": "review"})
    assert len(db.get_session(sid)["review_ids"]) == 2
    assert client.get("/api/review/today?domain=en").json()["total_due"] == 2

    # 2) Aluno responde; tutor avalia R1 como acerto
    fake_llm(FakeProvider("fake", tokens=["[MENSAGEM]\nCorreto!\n[REVISAO]\n- R1: acertou"]))
    client.post("/api/chat/stream", json={"session_id": sid, "message": "I went to the beach yesterday."})
    assert len(db.get_session(sid)["review_ids"]) == 1
    today = client.get("/api/review/today?domain=en").json()
    assert today["total_due"] == 1 and today["done_today"] == 1 and today["streak"] == 1

    prog = client.get("/api/progress?domain=en&days=7").json()
    assert prog["series"][-1]["reviews"] == 1 and prog["series"][-1]["correct"] == 1


def test_review_judge_grades_when_tutor_forgets(client, fake_llm):
    import review as rv

    class SmartFake(FakeProvider):
        async def stream(self, messages, temperature, fast=False):
            if "Você avalia uma sessão de revisão" in messages[0]["content"]:
                yield '{"R1": "acertou", "R2": "ausente"}'
            else:
                yield "[MENSAGEM]\nNice! What else did you do?"

    with db.session_scope() as s:
        for t in ["usa 'go' no passado", "esquece o 'the'"]:
            s.add(rv.Mistake(domain="en", text=t, norm=t, first_seen=rv.utcnow(), last_seen=rv.utcnow()))
    fake_llm(SmartFake("fake"))
    sid = client.post("/api/sessions", json={"domain": "en"}).json()["id"]
    client.post("/api/chat/stream", json={"session_id": sid, "message": "Revisar", "action": "review"})
    client.post("/api/chat/stream", json={"session_id": sid, "message": "I went to the park."})

    assert len(db.get_session(sid)["review_ids"]) == 1          # R1 avaliado, R2 segue pendente
    assert client.get("/api/review/today?domain=en").json()["done_today"] == 1


def test_off_topic_question_is_flagged_as_not_in_sources(client, fake_llm, monkeypatch):
    import library
    import reranker
    seen = {}

    class Spy(FakeProvider):
        async def stream(self, messages, temperature, fast=False):
            seen["system"] = messages[0]["content"]
            yield "[MENSAGEM]\nIsso não está nos seus livros."

    monkeypatch.setattr(library, "search", lambda *a, **k: [
        {"book_id": "b", "book": "Livro", "section": "s", "page_start": 1, "page_end": 1,
         "kind": "text", "content": "x", "vsim": 0.38}])
    fake_llm(Spy("fake"))
    sid = client.post("/api/sessions", json={"domain": "math_ml", "book_ids": ["b"]}).json()["id"]
    client.post("/api/chat/stream", json={"session_id": sid, "message": "receita de bolo"})
    assert "NÃO têm trechos relevantes" in seen["system"]
    assert "MATERIAIS DE REFERÊNCIA" not in seen["system"]
