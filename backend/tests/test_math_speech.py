import pytest

from math_speech import latex_to_speech, speak_math


@pytest.mark.parametrize("latex, expected", [
    (r"\frac{\partial L}{\partial w}", "derivada parcial de L em relação a w"),
    (r"\frac{dy}{dx}", "derivada de y em relação a x"),
    (r"\frac{a}{b}", "a sobre b"),
    (r"x^2 + y^2 = 1", "x ao quadrado mais y ao quadrado igual a 1"),
    (r"\sum_{i=1}^{n} x_i", "somatório de i igual a 1 até n de x índice i"),
    (r"\int_a^b f(x)\,dx", "integral de a até b de f x d x"),
    (r"A^T", "A transposta"),
    (r"A^{-1}", "A inversa"),
    (r"\sqrt{x}", "raiz quadrada de x"),
    (r"\|w\|_2", "norma 2 de w"),
    (r"\nabla f", "gradiente de f"),
    (r"\theta \in \mathbb{R}^n", "teta pertence a reais elevado a n"),
    (r"\lambda \geq 0", "lambda maior ou igual a 0"),
    (r"\hat{y}", "y chapéu"),
    (r"\lim_{x \to 0} f(x)", "limite quando x tende a 0 f x"),
    (r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}", "uma matriz"),
])
def test_portuguese(latex, expected):
    assert latex_to_speech(latex, "pt") == expected


def test_english_and_spanish():
    assert latex_to_speech(r"\frac{\partial L}{\partial w}", "en") == "partial derivative of L with respect to w"
    assert latex_to_speech(r"x^2", "en") == "x squared"
    assert latex_to_speech(r"\sum_{i=1}^{n} x_i", "es") == "sumatoria de i igual a 1 a n de x subíndice i"


def test_never_reads_raw_commands():
    out = latex_to_speech(r"\mathcal{L}(\boldsymbol{\theta}) = \operatorname{softplus}(z) \weirdcmd", "pt")
    assert "\\" not in out and "mathcal" not in out and "weirdcmd" not in out


def test_speak_math_replaces_all_delimiters():
    text = r"A perda é $L = \frac{1}{n}\sum_i e_i^2$ e o gradiente \(\nabla L\). Veja: $$w^T x$$"
    out = speak_math(text, "pt")
    assert "$" not in out and "\\(" not in out
    assert "1 sobre n" in out and "gradiente de L" in out and "w transposta x" in out


def test_assignment_arrow():
    assert latex_to_speech(r"w \leftarrow w - \eta \nabla L", "pt") == "w recebe w menos eta gradiente de L"
    assert latex_to_speech(r"w \gets w - \eta g", "en") == "w gets w minus eta g"
