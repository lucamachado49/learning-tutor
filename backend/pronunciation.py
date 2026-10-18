"""
pronunciation.py — Avaliação de pronúncia por fonemas (100% local).

    referência (texto)  ──espeak──▶ fonemas esperados, por palavra
    gravação (áudio)    ──wav2vec2──▶ fonemas PRODUZIDOS (sons, não palavras)
    alinhamento (Needleman-Wunsch) ─▶ acerto / troca / omissão / som extra
                                  ─▶ nota por palavra e geral + dicas para brasileiros

Diferente do Whisper, o modelo de fonemas não "adivinha" a palavra pretendida:
se você disser /s/ em "think", ele escuta /s/.
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from model_lock import LOAD_LOCK

log = logging.getLogger("tutor.pronunciation")

PHONEME_MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"   # reconhecedor de fonemas multilíngue (IPA)
ESPEAK_LANG = {"en": "en-us", "es": "es"}

# ---------------------------------------------------------------------------
# Fonemas esperados (espeak, o mesmo do Kokoro)
# ---------------------------------------------------------------------------
_espeak_ready = False


def _setup_espeak() -> None:
    global _espeak_ready
    if _espeak_ready:
        return
    import espeakng_loader
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
    _espeak_ready = True


def words_of(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", text)


def expected_phones(text: str, lang: str) -> list[tuple[str, list[str]]]:
    """[(palavra, [fonemas])] para o texto de referência."""
    _setup_espeak()
    from phonemizer import phonemize
    from phonemizer.separator import Separator

    words = words_of(text)
    if not words:
        return []
    out = phonemize(
        words, language=ESPEAK_LANG[lang], backend="espeak",
        separator=Separator(phone=" ", word=""), strip=True, preserve_punctuation=False,
    )
    return [(w, split_phones(p)) for w, p in zip(words, out)]


def split_phones(s: str) -> list[str]:
    return [p for p in (normalize(x) for x in s.split()) if p]


def normalize(p: str) -> str:
    """Remove marcas de acento/tonicidade que não mudam o som avaliado."""
    p = unicodedata.normalize("NFC", p)
    return re.sub(r"[ˈˌ‿\-]", "", p).replace("g", "ɡ")


_VOWELS_SET = {"a", "e", "i", "o", "u", "ɪ", "ʊ", "ə", "ɐ", "ɛ", "ɔ", "æ", "ʌ", "ɑ", "ɒ", "ɜ", "ɚ",
               "iː", "uː", "ɑː", "ɔː", "ɜː", "aɪ", "aʊ", "eɪ", "oʊ", "ɔɪ", "əʊ", "ᵻ"}

# ---------------------------------------------------------------------------
# Equivalências (variações que NÃO são erro)
# ---------------------------------------------------------------------------
_EQUIV_GROUPS = [
    {"ɹ", "r", "ɻ"},                 # r inglês: variações de transcrição
    # vogais reduzidas/centrais; antes de "r" o schwa vira ɚ naturalmente ("the right")
    {"ə", "ɐ", "ʌ", "ɚ", "ɝ", "ɜː", "ɜ", "əɹ", "ɚː", "ɪ", "ᵻ"},
    {"i", "iː"}, {"u", "uː"}, {"ɑ", "ɑː"}, {"ɔ", "ɔː"},
    {"oʊ", "o", "əʊ"}, {"eɪ", "e"},
    {"ɔːɹ", "oːɹ", "ɔɹ", "oɹ", "ɔː", "oː"},
    {"ɾ", "ɾ̃"}, {"l", "ɫ"},
    {"β", "b"}, {"ð̞", "ð"}, {"ɣ", "ɡ"},   # alofones do espanhol
]
_EQUIV = {}
for group in _EQUIV_GROUPS:
    for ph in group:
        _EQUIV[ph] = frozenset(group)


def same_sound(a: str, b: str) -> bool:
    return a == b or (a in _EQUIV and b in _EQUIV[a])


# Palavras funcionais do inglês: na fala natural a vogal se reduz a schwa ("to" → tə, "has" → həz)
FUNCTION_WORDS_EN = {
    "a", "an", "the", "to", "of", "and", "or", "for", "from", "at", "as", "but", "than", "that",
    "can", "has", "have", "had", "was", "were", "are", "do", "does", "you", "your", "them",
    "some", "there", "would", "could", "should", "will", "just", "been", "her", "his", "him",
}
_REDUCED = {"ə", "ɐ", "ɪ", "ᵻ", "ɚ", "ʌ"}
_FLAP = {"t", "d"}       # entre vogais, o inglês americano vira "flap" (it is → "idiz")


_ES_ALLOPHONES = {("ð", "d"), ("d", "ð"), ("β", "b"), ("b", "β"), ("ɣ", "ɡ"), ("ɡ", "ɣ")}


def natural_variation(word: str, expected: str, got: Optional[str], lang: str) -> bool:
    if got is None:
        return False
    if lang == "es":
        return (expected, got) in _ES_ALLOPHONES
    if lang != "en":
        return False
    if expected in _FLAP and got == "ɾ":
        return True
    return word.lower() in FUNCTION_WORDS_EN and expected in _VOWELS_SET and got in _REDUCED


# ---------------------------------------------------------------------------
# Alinhamento esperado × produzido
# ---------------------------------------------------------------------------
@dataclass
class PhoneResult:
    expected: str
    got: Optional[str]      # None = omitido
    ok: bool


@dataclass
class WordResult:
    word: str
    phones: list[PhoneResult] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)   # sons a mais (ex.: vogal no fim)

    @property
    def score(self) -> int:
        total = len(self.phones) + 0.5 * len(self.extra)
        ok = sum(p.ok for p in self.phones)
        return round(100 * ok / total) if total else 0


_LINKS = {frozenset({"s"}), frozenset({"z"}), frozenset({"s", "z"}), frozenset({"t"}), frozenset({"d"}),
          frozenset({"t", "d"}), frozenset({"k"}), frozenset({"p"}), frozenset({"m"}), frozenset({"n"})}


def merge_links(expected: list[tuple[str, list[str]]]) -> tuple[list[tuple[str, list[str]]], dict[int, str]]:
    """Remove a consoante final que se funde com a inicial igual da palavra seguinte.

    Devolve (fonemas ajustados, {índice da palavra: consoante removida}).
    """
    out = [(w, list(ph)) for w, ph in expected]
    merged: dict[int, str] = {}
    for i in range(len(out) - 1):
        a, b = out[i][1], out[i + 1][1]
        if len(a) > 1 and b and frozenset({a[-1], b[0]}) in _LINKS:
            merged[i] = a.pop()
    return out, merged


def align(expected: list[tuple[str, list[str]]], produced: list[str], lang: str = "en") -> list[WordResult]:
    """Needleman-Wunsch: troca=1, omissão/inserção=1, equivalente=0."""
    exp = [(wi, ph) for wi, (_, phones) in enumerate(expected) for ph in phones]
    n, m = len(exp), len(produced)
    cost = np.zeros((n + 1, m + 1))
    cost[:, 0] = np.arange(n + 1)
    cost[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if same_sound(exp[i - 1][1], produced[j - 1]) else 1
            cost[i, j] = min(cost[i - 1, j - 1] + sub, cost[i - 1, j] + 1, cost[i, j - 1] + 1)

    words = [WordResult(w) for w, _ in expected]
    i, j = n, m
    steps = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i, j] == cost[i - 1, j - 1] + (0 if same_sound(exp[i - 1][1], produced[j - 1]) else 1):
            steps.append(("pair", i - 1, j - 1)); i -= 1; j -= 1
        elif i > 0 and cost[i, j] == cost[i - 1, j] + 1:
            steps.append(("del", i - 1, None)); i -= 1
        else:
            steps.append(("ins", i - 1, j - 1)); j -= 1   # som extra após o fonema esperado i-1
    for kind, ei, pj in reversed(steps):
        if kind == "pair":
            wi, ph = exp[ei]
            got = produced[pj]
            ok = same_sound(ph, got) or natural_variation(expected[wi][0], ph, got, lang)
            words[wi].phones.append(PhoneResult(ph, got, ok))
        elif kind == "del":
            wi, ph = exp[ei]
            words[wi].phones.append(PhoneResult(ph, None, False))
        else:
            wi = exp[ei][0] if ei >= 0 else 0
            if words:
                words[wi].extra.append(produced[pj])
    for a, b in zip(words, words[1:]):
        if a.phones and b.phones and a.phones[-1].got is None and a.phones[-1].expected == b.phones[0].expected:
            a.phones[-1].ok = True
    return words


# ---------------------------------------------------------------------------
# Dicas para falantes de português
# ---------------------------------------------------------------------------
TIPS_EN = {
    "θ": "Som do 'th' surdo (think, three): ponta da língua entre os dentes e sopre o ar — não é 's', 'f' nem 't'.",
    "ð": "Som do 'th' sonoro (this, the): língua entre os dentes vibrando a voz — não é 'd' nem 'z'.",
    "ɪ": "'i' curto e relaxado (ship, sit): mais aberto e breve que o 'i' do português.",
    "iː": "'i' longo e tenso (sheep, seat): sorria e alongue o som.",
    "æ": "'a' bem aberto (cat, bad): abra mais a boca, entre o 'é' e o 'á'.",
    "ʊ": "'u' curto e relaxado (book, good): lábios menos arredondados que o 'u' do português.",
    "h": "'h' aspirado (house, hello): só um sopro, sem o 'r' raspado do português.",
    "ɹ": "'r' inglês (red, very): curve a língua para trás sem encostar no céu da boca.",
    "ŋ": "'ng' (thing, sing): termina no fundo da boca, sem soltar um 'g' nem virar 'n'.",
    "l": "'l' no fim de sílaba (milk, school): mantenha a língua no céu da boca — não vire 'u'.",
    "z": "'z' sonoro (is, was): vibre as cordas vocais.",
    "v": "'v' (very, have): dentes no lábio de baixo, com voz — não troque por 'b'.",
    "w": "'w' (water, we): lábios arredondados, como um 'u' rápido.",
    "t": "'t' (time, tea): não vire 'tch' antes de 'i' (como no português 'tia').",
    "d": "'d' (did, day): não vire 'dj' antes de 'i' (como no português 'dia').",
}
TIPS_ES = {
    "x": "'j'/'g' do espanhol (jamón, gente): som raspado no fundo da garganta.",
    "ɲ": "'ñ' (español, año): parecido com o 'nh' do português.",
    "r": "'rr' (perro, rojo): vibre a ponta da língua várias vezes — não é o 'r' do português de 'rato'.",
    "ɾ": "'r' simples (pero, caro): um toque rápido da ponta da língua.",
    "s": "'s' entre vogais (casa, mesa): continua surdo, sem virar 'z' como no português.",
    "e": "'e' do espanhol: sempre fechado (como 'ê'), nunca aberto como 'é'.",
    "o": "'o' do espanhol: sempre fechado (como 'ô'), nunca aberto como 'ó'.",
    "l": "'l' no fim (español, sol): mantenha o 'l' — não vire 'u'.",
}
_VOWELS = set("aeiouɪʊəɐɛɔæʌɑɒɜɚy")


def tips_for(words: list[WordResult], lang: str) -> list[str]:
    table = TIPS_EN if lang == "en" else TIPS_ES
    tips: dict[str, str] = {}
    for w in words:
        for p in w.phones:
            if not p.ok and p.expected in table:
                tips.setdefault(p.expected, table[p.expected])
        # Vogal extra no fim da palavra (big → "bigui") ou no início (speak → "ispeak")
        if w.extra and any(set(x) & _VOWELS for x in w.extra) and w.phones:
            if w.phones[-1].expected not in _VOWELS:
                tips.setdefault("_epenthesis", "Evite acrescentar vogal no fim das palavras "
                                "(dog, não 'dógui'; big, não 'bigui'): termine na consoante.")
        if lang == "en" and w.word.lower().startswith(("sp", "st", "sk", "sm", "sn", "sl")):
            if w.phones and not w.phones[0].ok and w.phones[0].expected == "s":
                tips.setdefault("_s_cluster", "Palavras com 's' + consoante (speak, study): "
                                "comece direto no 's', sem 'i' antes ('ispeak').")
    return list(tips.values())


# ---------------------------------------------------------------------------
# Reconhecedor de fonemas (wav2vec2)
# ---------------------------------------------------------------------------
_model = None
_processor = None
_device = "cpu"
_lock = threading.Lock()


def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def _load():
    global _model, _processor, _device
    if _model is not None:
        return
    with LOAD_LOCK:
        if _model is not None:
            return
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC

        _setup_espeak()  # o tokenizer de fonemas também usa o phonemizer
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _processor = AutoProcessor.from_pretrained(PHONEME_MODEL)
        model = Wav2Vec2ForCTC.from_pretrained(PHONEME_MODEL)
        if _device == "cuda":
            model = model.half()
        _model = model.to(_device).eval()
        log.info("Modelo de fonemas pronto (%s)", _device)


def warm() -> None:
    """Carrega o modelo em segundo plano (a 1ª carga leva alguns segundos)."""
    if available():
        try:
            _load()
            recognize(np.zeros(16000, dtype=np.float32))
        except Exception as exc:
            log.warning("Modelo de fonemas não carregou: %s", exc)


def recognize(audio16k: np.ndarray) -> list[str]:
    """Fonemas produzidos na gravação (16 kHz mono)."""
    return recognize_with_logprobs(audio16k)[0]


def recognize_with_logprobs(audio16k: np.ndarray) -> tuple[list[str], np.ndarray]:
    """(fonemas produzidos, log-probabilidades [quadros × vocabulário])."""
    import torch

    _load()
    inputs = _processor(audio16k, sampling_rate=16000, return_tensors="pt")
    values = inputs.input_values.to(_device)
    if _device == "cuda":
        values = values.half()
    with torch.inference_mode():
        logits = _model(values).logits.float()
    logprobs = torch.log_softmax(logits, dim=-1)[0].cpu().numpy()
    ids = logits.argmax(dim=-1)
    return split_phones(_processor.batch_decode(ids)[0]), logprobs


# ---------------------------------------------------------------------------
# Checagem de confusões típicas (GOP — "goodness of pronunciation")
# ---------------------------------------------------------------------------
# O reconhecedor tende a "corrigir" sons pelo contexto ("I sink" vira "I think").
# Por isso, cada som esperado é alinhado ao seu trecho do áudio (alinhamento forçado CTC) e,
# ali dentro, comparamos a probabilidade do som certo com a dos sons que brasileiros
# costumam usar no lugar. Se o substituto for mais provável, é erro.
CONFUSIONS = {
    "en": {
        "θ": ["s", "f", "t"], "ð": ["d", "z", "v"],
        # (æ→a fica de fora: o modelo rotula o /æ/ nativo como "a";
        #  z→s também: o /z/ final ensurdece naturalmente — "please")
        "ɪ": ["iː", "i"], "iː": ["ɪ"], "æ": ["ɛ"], "ʊ": ["uː", "u"],
        "h": ["x", "ʁ", "χ"], "ɹ": ["ʁ", "x", "h"], "v": ["b"], "ŋ": ["n"],
    },
    "es": {
        "r": ["ɾ", "ʁ", "x"], "x": ["ʁ", "h"], "s": ["z"], "e": ["ɛ"], "o": ["ɔ"],
    },
}
# Decisão: margem (log-prob do substituto − do esperado) na palavra ISOLADA + no CONTEXTO.
# Calibrado com leituras sintéticas certas/erradas (Kokoro e Piper): erros somam ≳ 2,
# leituras corretas ficam abaixo na grande maioria.
GOP_THRESHOLD = 2.0
GOP_THRESHOLD_VOWEL = 4.0   # vogais: o modelo é menos confiável (erros reais ficaram ~7–8)


def _token_id(vocab: dict, phone: str) -> Optional[int]:
    if phone in vocab:
        return vocab[phone]
    base = phone.replace("ː", "")
    return vocab.get(base)


def ctc_force_align(logprobs: np.ndarray, targets: list[int], blank: int = 0) -> list[list[int]]:
    """Viterbi CTC: devolve, para cada alvo, os índices de quadro atribuídos a ele."""
    T, L = logprobs.shape[0], len(targets)
    S = 2 * L + 1
    labels = [blank if s % 2 == 0 else targets[s // 2] for s in range(S)]
    NEG = -1e30
    dp = np.full((T, S), NEG)
    back = np.zeros((T, S), dtype=np.int32)
    dp[0, 0] = logprobs[0, blank]
    if S > 1:
        dp[0, 1] = logprobs[0, labels[1]]
    for t in range(1, T):
        lp = logprobs[t]
        for s in range(S):
            best, arg = dp[t - 1, s], s
            if s >= 1 and dp[t - 1, s - 1] > best:
                best, arg = dp[t - 1, s - 1], s - 1
            if s >= 2 and labels[s] != blank and labels[s] != labels[s - 2] and dp[t - 1, s - 2] > best:
                best, arg = dp[t - 1, s - 2], s - 2
            dp[t, s] = best + lp[labels[s]]
            back[t, s] = arg
    s = S - 1 if S == 1 or dp[T - 1, S - 1] >= dp[T - 1, S - 2] else S - 2
    frames: list[list[int]] = [[] for _ in range(L)]
    for t in range(T - 1, -1, -1):
        if s % 2 == 1:
            frames[s // 2].append(t)
        s = back[t, s]
    return frames


FRAME_SAMPLES = 320          # wav2vec2: 1 quadro = 20 ms a 16 kHz


def _best_confusion(logprobs: np.ndarray, frames: list[int], exp_id: int, alts: list[str], vocab: dict):
    seg = logprobs[frames]
    lp_exp = float(seg[:, exp_id].mean())
    best_alt, lp_alt = None, -1e30
    for alt in alts:
        aid = _token_id(vocab, alt)
        if aid is not None:
            v = float(seg[:, aid].mean())
            if v > lp_alt:
                best_alt, lp_alt = alt, v
    return best_alt, lp_alt - lp_exp


def confusion_check(words: list[WordResult], expected: list[tuple[str, list[str]]],
                    logprobs: np.ndarray, lang: str, audio16k: Optional[np.ndarray] = None) -> None:
    """Marca como erro os sons em que um substituto típico é mais provável (altera `words`).

    Palavras com sons críticos são reavaliadas ISOLADAS (recortadas do áudio): na frase
    inteira, o modelo "corrige" pelo contexto ("I sink it is…" soa como "I think…").
    """
    vocab = _processor.tokenizer.get_vocab()
    table = CONFUSIONS.get(lang, {})
    flat = [(wi, pi, ph) for wi, (_, phones) in enumerate(expected) for pi, ph in enumerate(phones)]
    ids = [_token_id(vocab, ph) for _, _, ph in flat]
    keep = [k for k, i in enumerate(ids) if i is not None]
    if not keep or logprobs.shape[0] < len(keep):
        return
    segments = ctc_force_align(logprobs, [ids[k] for k in keep])
    frames_of = {flat[k][:2]: f for k, f in zip(keep, segments)}

    # Limites de cada palavra (o CTC marca só 1–2 quadros por som; o recorte vai do meio
    # do intervalo com a palavra anterior até o meio do intervalo com a seguinte)
    spans: list[Optional[tuple[int, int]]] = []
    for wi, (_, phones) in enumerate(expected):
        fr = [t for pi in range(len(phones)) for t in frames_of.get((wi, pi), [])]
        spans.append((min(fr), max(fr)) if fr else None)

    def cut(wi: int) -> Optional[tuple[int, int]]:
        if spans[wi] is None:
            return None
        prev = next((spans[j] for j in range(wi - 1, -1, -1) if spans[j]), None)
        nxt = next((spans[j] for j in range(wi + 1, len(spans)) if spans[j]), None)
        lo = 0 if prev is None else (prev[1] + spans[wi][0]) // 2
        hi = logprobs.shape[0] - 1 if nxt is None else (spans[wi][1] + nxt[0]) // 2
        return lo * FRAME_SAMPLES, (hi + 1) * FRAME_SAMPLES

    for wi, (word, phones) in enumerate(expected):
        critical = [pi for pi, ph in enumerate(phones) if ph in table and (wi, pi) in frames_of]
        bounds = cut(wi)
        if not critical or bounds is None or audio16k is None:
            continue
        a, b = bounds
        w_ids = [_token_id(vocab, ph) for ph in phones]
        if b - a < 1600 or any(i is None for i in w_ids):
            continue
        _, iso_lp = recognize_with_logprobs(audio16k[a:b])
        if iso_lp.shape[0] < len(w_ids):
            continue
        iso_frames = ctc_force_align(iso_lp, w_ids)

        for pi in critical:
            ph = phones[pi]
            exp_id = w_ids[pi]
            alt, m_iso = _best_confusion(iso_lp, iso_frames[pi], exp_id, table[ph], vocab)
            if not alt:
                continue
            ctx_seg = logprobs[frames_of[(wi, pi)]]
            m_ctx = float(ctx_seg[:, vocab[alt]].mean() - ctx_seg[:, exp_id].mean()) if alt in vocab else 0.0
            result = words[wi].phones[pi]
            limit = GOP_THRESHOLD_VOWEL if ph in _VOWELS_SET else GOP_THRESHOLD
            if m_iso + m_ctx > limit and result.ok:
                result.ok, result.got = False, alt


# ---------------------------------------------------------------------------
# API de alto nível
# ---------------------------------------------------------------------------
def assess(audio16k: np.ndarray, reference: str, lang: str) -> dict:
    if lang not in ESPEAK_LANG:
        raise ValueError("Avaliação de pronúncia disponível para inglês e espanhol.")
    expected = expected_phones(reference, lang)
    if not expected:
        raise ValueError("Frase de referência vazia.")
    expected, merged = merge_links(expected)
    produced, logprobs = recognize_with_logprobs(audio16k)
    words = align(expected, produced, lang)
    for wi, consonant in merged.items():
        # se o aluno pronunciou a consoante mesmo assim, não é "som extra"
        pair = {consonant, "z" if consonant == "s" else "s" if consonant == "z" else consonant}
        words[wi].extra = [x for x in words[wi].extra if x not in pair]
    confusion_check(words, expected, logprobs, lang, audio16k)

    total = sum(len(w.phones) for w in words)
    overall = round(sum(w.score * len(w.phones) for w in words) / total) if total else 0
    return {
        "score": overall,
        "reference": reference,
        "produced": " ".join(produced),
        "words": [{
            "word": w.word, "score": w.score, "extra": w.extra,
            "phones": [{"expected": p.expected, "got": p.got, "ok": p.ok} for p in w.phones],
        } for w in words],
        "tips": tips_for(words, lang),
        # sons esperados com erro → alimentam o mapa de domínio
        "weak_sounds": sorted({p.expected for w in words for p in w.phones if not p.ok}),
    }
