"""
math_speech.py — Converte LaTeX em fala natural (pt, en, es) para o TTS.

    \\frac{\\partial L}{\\partial w}   → "derivada parcial de L em relação a w"
    \\sum_{i=1}^{n} x_i^2              → "somatório de i igual a 1 até n de x índice i ao quadrado"
    \\| x \\|_2                        → "norma 2 de x"

Determinístico (sem LLM, sem alucinação). O Speech Rule Engine (usado por leitores de tela)
não tem português, e o modo voz em português é o dos domínios técnicos — onde as fórmulas
aparecem. Construções desconhecidas são lidas de forma simples (letras/números), nunca como
comandos crus ("barra frac").
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Vocabulário por idioma
# ---------------------------------------------------------------------------
W = {
    "pt": {
        "frac": "{a} sobre {b}", "frac_simple": "{a} sobre {b}",
        "pdiff": "derivada parcial de {a} em relação a {b}", "diff": "derivada de {a} em relação a {b}",
        "sqrt": "raiz quadrada de {a}", "nroot": "raiz {n} de {a}",
        "sq": "ao quadrado", "cube": "ao cubo", "pow": "elevado a {a}", "transpose": "transposta",
        "inverse": "inversa", "sub": "índice {a}",
        "sum": "somatório", "prod": "produtório", "int": "integral", "lim": "limite",
        "from_to": "de {a} até {b}", "from": "de {a}", "of": "de", "when": "quando",
        "norm": "norma de {a}", "normk": "norma {k} de {a}", "abs": "módulo de {a}",
        "matrix": "uma matriz", "vec": "vetor {a}", "hat": "{a} chapéu", "bar": "{a} barra",
        "tilde": "{a} til", "dot": "{a} ponto", "star": "{a} estrela", "prime": "{a} linha",
        "grad": "gradiente de", "set_R": "reais", "set_N": "naturais", "set_Z": "inteiros",
        "set_E": "esperança de", "set_P": "probabilidade de",
        "ops": {
            "=": "igual a", "+": "mais", "-": "menos", "\\pm": "mais ou menos", "\\cdot": "vezes",
            "\\times": "vezes", "/": "dividido por", "<": "menor que", ">": "maior que",
            "\\leq": "menor ou igual a", "\\le": "menor ou igual a", "\\geq": "maior ou igual a",
            "\\ge": "maior ou igual a", "\\neq": "diferente de", "\\approx": "aproximadamente",
            "\\sim": "segue a distribuição", "\\propto": "proporcional a", "\\in": "pertence a",
            "\\notin": "não pertence a", "\\subset": "contido em", "\\subseteq": "contido em",
            "\\to": "tende a", "\\rightarrow": "vai para", "\\leftarrow": "recebe", "\\gets": "recebe",
            "\\coloneqq": "é definido como", "\\triangleq": "é definido como", "\\equiv": "equivale a", "\\mapsto": "leva em", "\\infty": "infinito",
            "\\Rightarrow": "implica", "\\iff": "se e somente se", "\\Leftrightarrow": "se e somente se",
            "\\forall": "para todo", "\\exists": "existe", "\\cup": "união", "\\cap": "interseção",
            "\\nabla": "gradiente de", "\\partial": "derivada parcial de", "\\ldots": "e assim por diante",
            "\\cdots": "e assim por diante", "\\dots": "e assim por diante", ",": ",", "|": "dado",
            "\\mid": "dado", "\\otimes": "produto tensorial", "\\circ": "composta com",
            "\\log": "log de", "\\ln": "logaritmo natural de", "\\exp": "exponencial de",
            "\\sin": "seno de", "\\cos": "cosseno de", "\\tan": "tangente de", "\\det": "determinante de",
            "\\max": "máximo de", "\\min": "mínimo de", "\\arg": "argumento", "\\argmax": "argumento máximo de",
            "\\argmin": "argumento mínimo de", "\\tr": "traço de", "\\operatorname{tr}": "traço de",
            "\\sigma": "sigma", "!": "fatorial",
        },
    },
    "en": {
        "frac": "{a} over {b}", "frac_simple": "{a} over {b}",
        "pdiff": "partial derivative of {a} with respect to {b}", "diff": "derivative of {a} with respect to {b}",
        "sqrt": "square root of {a}", "nroot": "{n}-th root of {a}",
        "sq": "squared", "cube": "cubed", "pow": "to the power of {a}", "transpose": "transpose",
        "inverse": "inverse", "sub": "sub {a}",
        "sum": "sum", "prod": "product", "int": "integral", "lim": "limit",
        "from_to": "from {a} to {b}", "from": "over {a}", "of": "of", "when": "as",
        "norm": "norm of {a}", "normk": "{k}-norm of {a}", "abs": "absolute value of {a}",
        "matrix": "a matrix", "vec": "vector {a}", "hat": "{a} hat", "bar": "{a} bar",
        "tilde": "{a} tilde", "dot": "{a} dot", "star": "{a} star", "prime": "{a} prime",
        "grad": "gradient of", "set_R": "the reals", "set_N": "the naturals", "set_Z": "the integers",
        "set_E": "expectation of", "set_P": "probability of",
        "ops": {
            "=": "equals", "+": "plus", "-": "minus", "\\pm": "plus or minus", "\\cdot": "times",
            "\\times": "times", "/": "divided by", "<": "less than", ">": "greater than",
            "\\leq": "less than or equal to", "\\le": "less than or equal to",
            "\\geq": "greater than or equal to", "\\ge": "greater than or equal to",
            "\\neq": "not equal to", "\\approx": "approximately", "\\sim": "is distributed as",
            "\\propto": "proportional to", "\\in": "in", "\\notin": "not in", "\\subset": "subset of",
            "\\subseteq": "subset of", "\\to": "goes to", "\\rightarrow": "goes to",
            "\\leftarrow": "gets", "\\gets": "gets", "\\coloneqq": "is defined as",
            "\\triangleq": "is defined as", "\\equiv": "is equivalent to", "\\mapsto": "maps to",
            "\\infty": "infinity", "\\Rightarrow": "implies", "\\iff": "if and only if",
            "\\Leftrightarrow": "if and only if", "\\forall": "for all", "\\exists": "there exists",
            "\\cup": "union", "\\cap": "intersection", "\\nabla": "gradient of",
            "\\partial": "partial of", "\\ldots": "and so on", "\\cdots": "and so on", "\\dots": "and so on",
            ",": ",", "|": "given", "\\mid": "given", "\\otimes": "tensor product", "\\circ": "composed with",
            "\\log": "log of", "\\ln": "natural log of", "\\exp": "exponential of", "\\sin": "sine of",
            "\\cos": "cosine of", "\\tan": "tangent of", "\\det": "determinant of", "\\max": "max of",
            "\\min": "min of", "\\arg": "arg", "\\argmax": "arg max of", "\\argmin": "arg min of",
            "\\tr": "trace of", "\\operatorname{tr}": "trace of", "\\sigma": "sigma", "!": "factorial",
        },
    },
    "es": {
        "frac": "{a} sobre {b}", "frac_simple": "{a} sobre {b}",
        "pdiff": "derivada parcial de {a} con respecto a {b}", "diff": "derivada de {a} con respecto a {b}",
        "sqrt": "raíz cuadrada de {a}", "nroot": "raíz {n} de {a}",
        "sq": "al cuadrado", "cube": "al cubo", "pow": "elevado a {a}", "transpose": "traspuesta",
        "inverse": "inversa", "sub": "subíndice {a}",
        "sum": "sumatoria", "prod": "productoria", "int": "integral", "lim": "límite",
        "from_to": "de {a} a {b}", "from": "sobre {a}", "of": "de", "when": "cuando",
        "norm": "norma de {a}", "normk": "norma {k} de {a}", "abs": "valor absoluto de {a}",
        "matrix": "una matriz", "vec": "vector {a}", "hat": "{a} sombrero", "bar": "{a} barra",
        "tilde": "{a} tilde", "dot": "{a} punto", "star": "{a} estrella", "prime": "{a} prima",
        "grad": "gradiente de", "set_R": "los reales", "set_N": "los naturales", "set_Z": "los enteros",
        "set_E": "esperanza de", "set_P": "probabilidad de",
        "ops": {
            "=": "igual a", "+": "más", "-": "menos", "\\pm": "más o menos", "\\cdot": "por",
            "\\times": "por", "/": "dividido por", "<": "menor que", ">": "mayor que",
            "\\leq": "menor o igual a", "\\le": "menor o igual a", "\\geq": "mayor o igual a",
            "\\ge": "mayor o igual a", "\\neq": "distinto de", "\\approx": "aproximadamente",
            "\\sim": "se distribuye como", "\\propto": "proporcional a", "\\in": "pertenece a",
            "\\notin": "no pertenece a", "\\subset": "contenido en", "\\subseteq": "contenido en",
            "\\to": "tiende a", "\\rightarrow": "va a", "\\leftarrow": "recibe", "\\gets": "recibe",
            "\\coloneqq": "se define como", "\\triangleq": "se define como", "\\equiv": "equivale a", "\\mapsto": "lleva a", "\\infty": "infinito",
            "\\Rightarrow": "implica", "\\iff": "si y solo si", "\\Leftrightarrow": "si y solo si",
            "\\forall": "para todo", "\\exists": "existe", "\\cup": "unión", "\\cap": "intersección",
            "\\nabla": "gradiente de", "\\partial": "derivada parcial de", "\\ldots": "etcétera",
            "\\cdots": "etcétera", "\\dots": "etcétera", ",": ",", "|": "dado", "\\mid": "dado",
            "\\otimes": "producto tensorial", "\\circ": "compuesta con", "\\log": "logaritmo de",
            "\\ln": "logaritmo natural de", "\\exp": "exponencial de", "\\sin": "seno de",
            "\\cos": "coseno de", "\\tan": "tangente de", "\\det": "determinante de",
            "\\max": "máximo de", "\\min": "mínimo de", "\\arg": "argumento", "\\argmax": "argumento máximo de",
            "\\argmin": "argumento mínimo de", "\\tr": "traza de", "\\operatorname{tr}": "traza de",
            "\\sigma": "sigma", "!": "factorial",
        },
    },
}

GREEK = {
    "alpha": "alfa", "beta": "beta", "gamma": "gama", "delta": "delta", "epsilon": "épsilon",
    "varepsilon": "épsilon", "zeta": "zeta", "eta": "eta", "theta": "teta", "vartheta": "teta",
    "iota": "iota", "kappa": "capa", "lambda": "lambda", "mu": "mi", "nu": "ni", "xi": "csi",
    "pi": "pi", "rho": "rô", "sigma": "sigma", "tau": "tau", "phi": "fi", "varphi": "fi",
    "chi": "qui", "psi": "psi", "omega": "ômega",
}
GREEK_EN = {"gamma": "gamma", "mu": "mu", "nu": "nu", "xi": "xi", "rho": "rho", "phi": "phi",
            "chi": "chi", "omega": "omega", "kappa": "kappa", "epsilon": "epsilon", "theta": "theta"}

_STYLE = {"mathbf", "boldsymbol", "bm", "mathrm", "mathit", "text", "textbf", "mathsf", "operatorname",
          "mathcal", "left", "right", "big", "Big", "bigg", "Bigg", "displaystyle", "limits"}
_IGNORE = {"\\,", "\\;", "\\:", "\\!", "\\quad", "\\qquad", "&", "\\\\", "\\left", "\\right"}


# ---------------------------------------------------------------------------
# Tokenizador e parser recursivo (subconjunto de LaTeX usado em ML)
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r"\\[a-zA-Z]+|\\.|[{}^_]|\d+(?:\.\d+)?|[a-zA-Z]|\S")


class _Parser:
    def __init__(self, latex: str, lang: str):
        self.t = [tok for tok in _TOKEN.findall(latex) if tok not in _IGNORE]
        self.i = 0
        self.w = W[lang]
        self.lang = lang

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def group(self) -> str:
        """Lê um argumento: {…} ou um único átomo."""
        if self.peek() == "{":
            self.next()
            out = self.seq(stop="}")
            self.next()  # }
            return out
        return self.atom()

    def raw_group(self) -> str:
        """Conteúdo cru de {…} (para \\begin{matrix} etc.)."""
        if self.peek() != "{":
            return self.next() or ""
        self.next()
        depth, out = 1, []
        while self.peek() is not None:
            tok = self.next()
            depth += tok == "{"
            depth -= tok == "}"
            if depth == 0:
                break
            out.append(tok)
        return "".join(out)

    def seq(self, stop=None) -> str:
        parts = []
        while self.peek() is not None and self.peek() != stop:
            parts.append(self.postfix(self.atom()))
        return " ".join(p for p in parts if p)

    def postfix(self, base: str) -> str:
        """Índices e expoentes após um átomo: x_i^2, A^T, A^{-1}."""
        w = self.w
        while self.peek() in ("_", "^", "'"):
            op = self.next()
            if op == "'":
                base = w["prime"].format(a=base)
                continue
            arg = self.group()
            if op == "_":
                base = f"{base} {w['sub'].format(a=arg)}"
            elif arg in ("2",):
                base = f"{base} {w['sq']}"
            elif arg in ("3",):
                base = f"{base} {w['cube']}"
            elif arg in ("T", "\\top", "⊤") or arg == "":
                base = f"{base} {w['transpose']}"
            elif arg in (self.w["ops"]["-"] + " 1", "-1"):
                base = f"{base} {w['inverse']}"
            else:
                base = f"{base} {w['pow'].format(a=arg)}"
        return base

    def bigop(self, name: str) -> str:
        """\\sum, \\prod, \\int, \\lim com limites."""
        w = self.w
        lo = hi = None
        while self.peek() in ("_", "^"):
            if self.next() == "_":
                lo = self.group()
            else:
                hi = self.group()
        if name == "lim":
            return f"{w['lim']} {w['when']} {lo}" if lo else w["lim"]
        head = w[name]
        if lo and hi:
            head += " " + w["from_to"].format(a=lo, b=hi)
        elif lo:
            head += " " + w["from"].format(a=lo)
        return f"{head} {w['of']}"

    def atom(self) -> str:
        tok = self.next()
        w = self.w
        if tok is None or tok == "}":
            return ""
        if tok == "{":
            out = self.seq(stop="}")
            self.next()
            return out
        if tok.startswith("\\"):
            name = tok[1:]
            if name == "frac" or name in ("dfrac", "tfrac"):
                a, b = self.group(), self.group()
                # ∂L/∂w e dL/dw viram "derivada parcial de L em relação a w"
                for key, prefix in (("pdiff", w["ops"]["\\partial"]), ("diff", None)):
                    if key == "pdiff" and a.startswith(prefix) and b.startswith(prefix):
                        return w["pdiff"].format(a=a[len(prefix):].strip() or "", b=b[len(prefix):].strip())
                if re.fullmatch(r"d\s*\S.*", a) and re.fullmatch(r"d\s*\S+", b) and a.split()[0] == "d":
                    return w["diff"].format(a=a[1:].strip(), b=b[1:].strip())
                return w["frac"].format(a=a, b=b)
            if name == "sqrt":
                n = None
                if self.peek() == "[":
                    self.next(); n = []
                    while self.peek() not in ("]", None):
                        n.append(self.next())
                    self.next(); n = "".join(n)
                a = self.group()
                return w["nroot"].format(n=n, a=a) if n else w["sqrt"].format(a=a)
            if name in ("sum", "prod", "int", "iint", "oint", "lim"):
                return self.bigop("int" if name in ("iint", "oint") else name)
            if name in ("begin",):
                env = self.raw_group()
                while self.peek() is not None and not (self.peek() == "\\end"):
                    self.next()
                self.next(); self.raw_group()
                return w["matrix"] if "matrix" in env or env == "array" else ""
            if name in ("mathbb", "mathbbm"):
                letter = self.raw_group()
                return w.get(f"set_{letter}", letter)
            if name in ("vec",):
                return w["vec"].format(a=self.group())
            if name in ("hat", "widehat", "bar", "overline", "tilde", "widetilde", "dot"):
                key = {"widehat": "hat", "overline": "bar", "widetilde": "tilde"}.get(name, name)
                return w[key].format(a=self.group())
            if name in ("mathbb",):
                return self.group()
            if name in _STYLE:
                return self.group() if self.peek() == "{" else ""
            if name in ("|", "Vert", "lVert", "rVert"):
                inner = self.seq_until({"\\|", "\\Vert", "\\rVert"})
                k = None
                if self.peek() == "_":
                    self.next(); k = self.group()
                return w["normk"].format(k=k, a=inner) if k else w["norm"].format(a=inner)
            if name in ("lvert",):
                inner = self.seq_until({"\\rvert"})
                return w["abs"].format(a=inner)
            if tok in w["ops"]:
                return w["ops"][tok]
            if name in GREEK:
                g = GREEK_EN.get(name, GREEK[name]) if self.lang == "en" else GREEK[name]
                return g
            if name.capitalize() != name and name.lower() in GREEK:
                return GREEK[name.lower()]
            return ""  # comando desconhecido: silencia (nunca "barra comando")
        if tok == "|":
            inner = self.seq_until({"|"})
            return w["abs"].format(a=inner) if inner else w["ops"]["|"]
        if tok in ("(", ")", "[", "]"):
            return ""
        if tok in w["ops"]:
            return w["ops"][tok]
        if tok == "*":
            return "estrela" if self.lang == "pt" else "star" if self.lang == "en" else "estrella"
        return tok

    def seq_until(self, closers: set) -> str:
        parts = []
        while self.peek() is not None and self.peek() not in closers:
            parts.append(self.postfix(self.atom()))
        self.next()  # fechamento
        return " ".join(p for p in parts if p)


def latex_to_speech(latex: str, lang: str = "pt") -> str:
    lang = lang if lang in W else "en"
    try:
        out = _Parser(latex, lang).seq()
    except Exception:
        out = ""
    out = re.sub(r"\s+", " ", out).strip(" ,")
    return out or ({"pt": "fórmula", "en": "formula", "es": "fórmula"}[lang])


_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE = re.compile(r"(?<!\$)\$([^$\n]+?)\$(?!\$)")
_PAREN = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)


def speak_math(text: str, lang: str = "pt") -> str:
    """Substitui todas as fórmulas ($…$, $$…$$, \\(…\\), \\[…\\]) do texto pela versão falada."""
    conv = lambda m: f" {latex_to_speech(m.group(1), lang)} "
    for rx in (_DISPLAY, _BRACKET, _PAREN, _INLINE):
        text = rx.sub(conv, text)
    return text
