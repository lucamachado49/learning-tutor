"""
verifier.py — Gabaritos calculados com SymPy (em vez de confiar na conta do LLM).

O LLM escreve expressões SymPy numa seção [VERIFICACAO]; aqui elas são:
  1. validadas por AST (só chamadas/atributos/operadores sobre nomes permitidos,
     sem import, sem atributos "_privados", sem lambdas/comprehensions);
  2. executadas num subprocesso Python isolado (-I) com timeout.

Formato aceito (uma instrução por linha):
    A = Matrix([[4, -2], [6, -1]])
    A.eigenvals()
    solve(x**2 - 3*x + 8, x)
"""

from __future__ import annotations

import ast
import json
import logging
import subprocess
import sys

log = logging.getLogger("tutor.verifier")

TIMEOUT_S = 8
MAX_LINES = 12

ALLOWED_NAMES = {
    # construtores e símbolos
    "Matrix", "eye", "zeros", "ones", "diag", "symbols", "Symbol", "Rational", "Integer", "Float",
    "S", "I", "pi", "E", "oo", "sqrt", "exp", "log", "sin", "cos", "tan", "atan", "Abs", "factorial",
    "binomial", "Sum", "Product", "Piecewise", "Eq",
    # cálculo e álgebra
    "diff", "integrate", "limit", "series", "simplify", "expand", "factor", "solve", "nsolve",
    "linsolve", "Derivative", "Integral", "hessian", "Poly", "roots", "nroots", "N", "re", "im",
    # probabilidade
    "Normal", "Bernoulli", "Binomial", "Die", "P", "E_", "variance", "density",
    # variáveis simbólicas comuns
    "x", "y", "z", "t", "w", "b", "n", "k", "mu", "sigma", "lam", "theta",
    # auxiliares definidos no runner
    "gradient", "grad", "jacobian",
    # tipos básicos
    "range", "len", "sum", "min", "max", "abs", "round", "list", "tuple",
}

_ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Call, ast.keyword,
    ast.Attribute, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Subscript, ast.Slice,
    ast.BinOp, ast.UnaryOp, ast.Compare, ast.operator, ast.unaryop, ast.cmpop,
)


class UnsafeCode(ValueError):
    pass


def validate(code: str) -> list[str]:
    """Valida o código e devolve as linhas não vazias. Lança UnsafeCode se algo for proibido."""
    lines = [ln.strip() for ln in code.strip().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        raise UnsafeCode("vazio")
    if len(lines) > MAX_LINES:
        raise UnsafeCode("linhas demais")

    assigned: set[str] = set()
    for line in lines:
        try:
            tree = ast.parse(line, mode="exec")
        except SyntaxError as exc:
            raise UnsafeCode(f"sintaxe inválida: {line}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_NODES):
                raise UnsafeCode(f"construção proibida: {type(node).__name__}")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                raise UnsafeCode("atributo privado")
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in ALLOWED_NAMES and node.id not in assigned:
                    raise UnsafeCode(f"nome não permitido: {node.id}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 50:
                raise UnsafeCode("string longa")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name) or target.id.startswith("_"):
                        raise UnsafeCode("atribuição inválida")
                    assigned.add(target.id)
    return lines


# Executado no subprocesso: monta o namespace só com o que está liberado
_RUNNER = r"""
import json, sys
import sympy
from sympy import stats
lines, allowed = json.loads(sys.stdin.read())
x, y, z, t, w, b, n, k, mu, sigma, lam, theta = sympy.symbols("x y z t w b n k mu sigma lam theta")
ns = {"__builtins__": {}}
for name in allowed:
    if hasattr(sympy, name):
        ns[name] = getattr(sympy, name)
    elif name in ("Normal", "Bernoulli", "Binomial", "Die", "P", "variance", "density"):
        ns[name] = getattr(stats, name)
ns["E_"] = stats.E
for name, val in dict(x=x, y=y, z=z, t=t, w=w, b=b, n=n, k=k, mu=mu, sigma=sigma, lam=lam, theta=theta).items():
    ns[name] = val
import builtins
for name in ("range", "len", "sum", "min", "max", "abs", "round", "list", "tuple"):
    ns[name] = getattr(builtins, name)
def gradient(f, variables):
    return sympy.Matrix([sympy.diff(f, v) for v in variables])
ns["gradient"] = ns["grad"] = gradient
ns["jacobian"] = lambda fs, variables: sympy.Matrix(fs).jacobian(list(variables))

import ast
out, last_name = [], None
for line in lines:
    tree = ast.parse(line)
    if isinstance(tree.body[0], ast.Assign):
        exec(compile(tree, "<v>", "exec"), ns)
        last_name = tree.body[0].targets[0].id
    else:
        out.append(f"{line}  →  {sympy.sstr(eval(compile(line, '<v>', 'eval'), ns))}")
if not out and last_name:
    out.append(f"{last_name}  →  {sympy.sstr(ns[last_name])}")
print(json.dumps(out))
"""


def run(code: str) -> str:
    """Executa o código validado; devolve as linhas 'expressão → resultado'. Lança em erro."""
    lines = validate(code)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _RUNNER],
        input=json.dumps([lines, sorted(ALLOWED_NAMES)]),
        capture_output=True, text=True, timeout=TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr else "falha")
    results = json.loads(proc.stdout)
    if not results:
        raise RuntimeError("nenhuma expressão avaliada")
    return "\n".join(results)


def try_run(code: str) -> str:
    """Versão tolerante: devolve '' se o código for inválido/inseguro ou falhar."""
    try:
        return run(code)
    except Exception as exc:
        log.warning("Verificação SymPy descartada: %s", exc)
        return ""
