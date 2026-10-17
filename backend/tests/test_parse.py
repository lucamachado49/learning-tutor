from main import _parse_response


def test_parse_all_sections():
    text = """[MENSAGEM]
Hello! How are you?

[FEEDBACK PEDAGÓGICO]
Use "went" no passado.

[ERROS]
- usa 'go' no lugar de 'went'
- esquece o artigo 'the'
"""
    msg, fb, errors = _parse_response(text)
    assert msg == "Hello! How are you?"
    assert fb == 'Use "went" no passado.'
    assert errors == ["usa 'go' no lugar de 'went'", "esquece o artigo 'the'"]


def test_parse_ignores_none_and_loose_lines():
    text = "[MENSAGEM]\nHi\n[FEEDBACK PEDAGÓGICO]\nÓtimo!\n[ERROS]\n- nenhum\nContinue praticando!"
    _, _, errors = _parse_response(text)
    assert errors == []


def test_parse_without_tags_uses_whole_text():
    msg, fb, errors = _parse_response("Just a plain answer.")
    assert (msg, fb, errors) == ("Just a plain answer.", "", [])


def test_parse_feedback_without_accent():
    msg, fb, _ = _parse_response("[MENSAGEM]\nOi\n[FEEDBACK PEDAGOGICO]\nBom")
    assert (msg, fb) == ("Oi", "Bom")


def test_parse_mastery_scores():
    from main import _parse_mastery
    text = "[MENSAGEM]\nok\n[DOMINIO]\n- regra da cadeia: 60\n- autovalores: 85/100\n- texto solto\n- nenhum"
    assert _parse_mastery(text) == [("regra da cadeia", 60.0), ("autovalores", 85.0)]


def test_message_excludes_hidden_sections():
    msg, fb, _ = _parse_response("[MENSAGEM]\nCalcule.\n[FEEDBACK PEDAGÓLICO]\nDica\n[VERIFICACAO]\nA.det()")
    assert msg == "Calcule." and fb == "Dica"


def test_used_citations():
    from main import _used_citations
    refs = [{"book_id": "b", "book": "L", "section": "s", "page_start": i, "page_end": i,
             "kind": "text", "content": f"<b>t{i}</b>"} for i in range(1, 6)]
    assert [c["n"] for c in _used_citations("como visto em [2] e [4]", refs)] == [2, 4]
    # sem citação explícita: só as 3 mais relevantes, com texto limpo
    cites = _used_citations("sem citação", refs)
    assert [c["n"] for c in cites] == [1, 2, 3] and cites[0]["snippet"] == "t1"


def test_grouped_citations():
    from main import _cited_numbers
    assert _cited_numbers("ver [2, 6] e [1-3]; também [5] mas não [x] nem [100]") == {1, 2, 3, 5, 6}


def test_message_falls_back_to_feedback_when_missing():
    msg, fb, _ = _parse_response("[FEEDBACK PEDAGÓGICO]\nUse 'went'. Where did you go next?\n[REVISAO]\n- R1: errou")
    assert msg.startswith("Use 'went'") and fb == ""


def test_message_tag_spelling_variants():
    for tag in ("MENSAGEM", "MESSAGEM", "MENSAJE", "MESSAGE"):
        msg, fb, _ = _parse_response(f"[{tag}]\nHi!\n[FEEDBACK PEDAGÓGICO]\nOk")
        assert (msg, fb) == ("Hi!", "Ok"), tag
