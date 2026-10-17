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
