import pytest

import verifier
from verifier import UnsafeCode


def test_computes_eigenvalues_and_gradient():
    out = verifier.run("A = Matrix([[1, 2], [3, 4]])\nA.eigenvals()")
    assert "sqrt(33)" in out
    out = verifier.run("g = grad(sin(x) + exp(y), [x, y])")
    assert "cos(x)" in out and "exp(y)" in out


@pytest.mark.parametrize("code", [
    '__import__("os").system("echo hacked")',
    "().__class__.__bases__",
    'open("secrets.txt")',
    "[c for c in range(3)]",
    "lambda: 1",
    "A = 1\nA.__dict__",
    "eval('1+1')",
    "Matrix._new",
])
def test_blocks_unsafe_code(code):
    with pytest.raises(UnsafeCode):
        verifier.validate(code)


def test_try_run_is_tolerant():
    assert verifier.try_run("isto não é código") == ""
    assert verifier.try_run("") == ""
