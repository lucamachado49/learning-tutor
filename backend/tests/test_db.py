import db


def test_session_crud():
    s = db.create_session("en", "B1", "conversation")
    assert db.get_session(s["id"])["domain"] == "en"

    db.update_session(s["id"], title="Novo título", level="B2")
    got = db.get_session(s["id"])
    assert (got["title"], got["level"]) == ("Novo título", "B2")

    db.delete_session(s["id"])
    assert db.get_session(s["id"]) is None


def test_messages_order_and_limit():
    s = db.create_session("es", "A2", "quiz")
    for i in range(5):
        db.add_message(s["id"], "user", f"m{i}")
    assert [m["content"] for m in db.get_messages(s["id"])] == ["m0", "m1", "m2", "m3", "m4"]
    # limit devolve as ÚLTIMAS mensagens, em ordem cronológica
    assert [m["content"] for m in db.get_messages(s["id"], limit=2)] == ["m3", "m4"]


def test_delete_session_removes_messages():
    s = db.create_session("en", "B1", "conversation")
    db.add_message(s["id"], "user", "oi")
    db.delete_session(s["id"])
    assert db.get_messages(s["id"]) == []


def test_mistakes_are_deduplicated_and_ranked():
    db.record_mistakes("en", ["Usa 'go' no lugar de 'went'", "esquece o 'the'"])
    db.record_mistakes("en", ["usa  'go' no lugar de 'went'"])  # mesma coisa, outra caixa/espaço
    db.record_mistakes("es", ["falso amigo: exquisito"])

    top = db.top_mistakes("en")
    assert len(top) == 2
    assert top[0]["count"] == 2 and "went" in top[0]["text"]

    db.delete_mistake(top[0]["id"])
    assert len(db.top_mistakes("en")) == 1
    assert len(db.top_mistakes("es")) == 1


def test_mastery_moving_average_and_order():
    db.record_mastery("math_ml", [("Regra da cadeia", 100)])
    db.record_mastery("math_ml", [("regra da cadeia", 0), ("Autovalores", 80)])
    m = db.get_mastery("math_ml")
    assert [x["concept"] for x in m] == ["Regra da cadeia", "Autovalores"]  # mais fraco primeiro
    assert m[0]["score"] == 60.0 and m[0]["attempts"] == 2                 # 0.6*100 + 0.4*0


def test_answer_key_of_last_assistant_message():
    s = db.create_session("math_ml", "Intermediário", "quiz")
    db.add_message(s["id"], "assistant", "Calcule det(A)", answer_key="A.det() → -2")
    assert db.last_answer_key(s["id"]) == "A.det() → -2"
    db.add_message(s["id"], "user", "-2")
    db.add_message(s["id"], "assistant", "Correto!")
    assert db.last_answer_key(s["id"]) == ""
    assert db.get_messages(s["id"])[0]["verified"] is True
