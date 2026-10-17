from tts import clean_for_speech


def test_clean_for_speech_removes_markup():
    text = (
        "**Gradiente**: $\\nabla f$ e\n$$w = w - \\eta g$$\n"
        "```python\nprint(1)\n```\nVeja [docs](http://x)."
    )
    out = clean_for_speech(text)
    assert "**" not in out and "$" not in out and "print" not in out and "http" not in out
    assert "Gradiente" in out and "docs" in out
