import library
from library import ChunkDraft, is_exercise_section, section_for_page, split_into_chunks

TOC = [
    [1, "Part I", 1],
    [2, "2 Linear Algebra", 2],
    [3, "2.1 Systems of Equations", 2],
    [3, "2.2 Matrices", 4],
    [2, "Exercises", 6],
    [1, "Part II", 8],
]


def test_section_for_page_tracks_nesting():
    assert section_for_page(TOC, 1) == "Part I"
    assert section_for_page(TOC, 3) == "Part I › 2 Linear Algebra › 2.1 Systems of Equations"
    assert section_for_page(TOC, 5) == "Part I › 2 Linear Algebra › 2.2 Matrices"
    # nível mais raso fecha os mais profundos
    assert section_for_page(TOC, 6) == "Part I › Exercises"
    assert section_for_page(TOC, 9) == "Part II"
    assert section_for_page([], 3) == ""


def test_exercise_detection_uses_only_leaf_title():
    assert is_exercise_section("Part I › Exercises")
    assert is_exercise_section("Cap. 3 › 3.9 Problems")
    assert is_exercise_section("Cap. 3 › Problems and Solutions")
    assert not is_exercise_section("Part II Central Machine Learning Problems › 9.2 Estimation")
    assert not is_exercise_section("Cap. 10 › 10.1 Problem Setting")


def test_split_respects_sections_and_size():
    pages = [
        (2, "Para A.\n\nPara B."),
        (3, "Para C."),
        (4, "x" * 250),        # nova seção (2.2) e parágrafo maior que o limite
        (6, "Exercise 1.\n\nExercise 2."),
    ]
    chunks = split_into_chunks(pages, TOC, max_chars=100)

    first = chunks[0]
    assert first.section.endswith("2.1 Systems of Equations")
    assert (first.page_start, first.page_end) == (2, 3)
    assert "Para A." in first.content and "Para C." in first.content

    matrices = [c for c in chunks if c.section.endswith("2.2 Matrices")]
    assert len(matrices) == 3 and all(len(c.content) <= 100 for c in matrices)

    assert chunks[-1].kind == "exercise" and "Exercise 2." in chunks[-1].content
    assert all(c.kind == "text" for c in chunks[:-1])


def test_build_tsquery_is_safe_or_query():
    q = library.build_tsquery("Regra da cadeia; DROP TABLE x; a'b")
    assert q == "regra | cadeia | drop | table"


def test_chunkdraft_defaults():
    d = ChunkDraft("s", 1, 1, "text", "")
    assert d.parts == []
