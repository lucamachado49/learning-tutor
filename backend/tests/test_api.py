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
