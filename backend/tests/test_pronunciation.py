import pronunciation as pr


def test_expected_phones_by_word():
    exp = pr.expected_phones("I think, this!", "en")
    assert [w for w, _ in exp] == ["I", "think", "this"]
    assert exp[1][1] == ["θ", "ɪ", "ŋ", "k"]
    assert exp[2][1][0] == "ð"


def test_perfect_match_scores_100():
    exp = [("think", ["θ", "ɪ", "ŋ", "k"])]
    words = pr.align(exp, ["θ", "ɪ", "ŋ", "k"])
    assert words[0].score == 100 and all(p.ok for p in words[0].phones)


def test_th_as_s_is_flagged_with_tip():
    exp = [("think", ["θ", "ɪ", "ŋ", "k"])]
    words = pr.align(exp, ["s", "ɪ", "ŋ", "k"])
    first = words[0].phones[0]
    assert (first.expected, first.got, first.ok) == ("θ", "s", False)
    assert words[0].score == 75
    assert any("língua entre os dentes" in t for t in pr.tips_for(words, "en"))


def test_epenthetic_vowel_at_word_end():
    exp = [("big", ["b", "ɪ", "ɡ"]), ("dog", ["d", "ɑː", "ɡ"])]
    words = pr.align(exp, ["b", "ɪ", "ɡ", "i", "d", "ɑ", "ɡ"])
    assert words[0].extra == ["i"] and words[0].score < 100
    assert words[1].score == 100                      # ɑ ≈ ɑː
    assert any("vogal no fim" in t for t in pr.tips_for(words, "en"))


def test_omitted_sound():
    exp = [("cats", ["k", "æ", "t", "s"])]
    words = pr.align(exp, ["k", "æ", "t"])
    assert words[0].phones[-1].got is None and not words[0].phones[-1].ok


def test_equivalent_variants_are_not_errors():
    assert pr.same_sound("ɹ", "r") and pr.same_sound("iː", "i")
    assert not pr.same_sound("ɪ", "iː")       # ship × sheep continua sendo erro


def test_spanish_tips():
    exp = pr.expected_phones("perro", "es")
    produced = [("x" if p == "r" else p) for p in exp[0][1]]
    words = pr.align(exp, produced)
    assert any("rr" in t for t in pr.tips_for(words, "es"))


def test_linking_consonants_are_merged():
    exp, merged = pr.merge_links(pr.expected_phones("this seat", "en"))
    assert exp[0][1][-1] != "s" and merged == {0: "s"}


def test_natural_variations_are_not_errors():
    assert pr.natural_variation("it", "t", "ɾ", "en")          # flap americano
    assert pr.natural_variation("to", "uː", "ə", "en")         # forma reduzida
    assert not pr.natural_variation("food", "uː", "ə", "en")   # palavra de conteúdo: é erro
    assert pr.natural_variation("rápido", "ð", "d", "es")      # alofone no espanhol
    assert not pr.natural_variation("this", "ð", "d", "en")    # no inglês ð→d é erro


def test_ctc_force_align_assigns_frames_in_order():
    import numpy as np
    lp = np.full((6, 4), -10.0)
    for t, tok in enumerate([1, 1, 0, 2, 2, 3]):
        lp[t, tok] = 0.0
    frames = pr.ctc_force_align(lp, [1, 2, 3])
    assert frames == [[0, 1], [3, 4], [5]] or [sorted(f) for f in frames] == [[0, 1], [3, 4], [5]]
