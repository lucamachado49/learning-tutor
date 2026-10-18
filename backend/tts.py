"""
tts.py — Síntese de voz local: Kokoro (natural) com fallback para Piper.
"""

from __future__ import annotations

import io
import logging
import re
import wave
from typing import Optional

import numpy as np

import config
from math_speech import speak_math

log = logging.getLogger("tutor.tts")

try:
    from kokoro_onnx import Kokoro  # type: ignore
    KOKORO_INSTALLED = True
except ImportError:
    KOKORO_INSTALLED = False

try:
    from piper import PiperVoice  # type: ignore
    PIPER_INSTALLED = True
except ImportError:
    PIPER_INSTALLED = False

# idioma de fala → (voz Kokoro, código espeak)
KOKORO_VOICES = {
    "en": ("af_heart", "en-us"),
    "es": ("ef_dora", "es"),
    "pt": ("pf_dora", "pt-br"),
}

PIPER_VOICES = {
    "en": "en_US-lessac-medium",
    "es": "es_ES-davefx-medium",
}


_CODE_ON_SCREEN = {"pt": "(código na tela)", "en": "(code on screen)", "es": "(código en pantalla)"}


def clean_for_speech(text: str, lang: str = "pt") -> str:
    """Prepara o texto para o TTS: fórmulas viram fala natural; código e markdown saem."""
    text = re.sub(r"```.*?```", f" {_CODE_ON_SCREEN.get(lang, '')} ", text, flags=re.DOTALL)
    # Fórmulas são LIDAS ("derivada parcial de L em relação a w"), não descartadas
    text = speak_math(text, lang)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>|]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buf.getvalue()


class KokoroTTS:
    name = "kokoro"

    def __init__(self) -> None:
        self._engine: Optional["Kokoro"] = None

    def available(self) -> bool:
        return KOKORO_INSTALLED and config.KOKORO_MODEL.exists() and config.KOKORO_VOICES.exists()

    def supports(self, lang: str) -> bool:
        return lang in KOKORO_VOICES

    def synthesize(self, text: str, lang: str, speed: float = 1.0) -> bytes:
        if self._engine is None:
            self._engine = Kokoro(str(config.KOKORO_MODEL), str(config.KOKORO_VOICES))
            log.info("Kokoro carregado: %s", config.KOKORO_MODEL.name)
        voice, espeak_lang = KOKORO_VOICES[lang]
        samples, sr = self._engine.create(text, voice=voice, speed=speed, lang=espeak_lang)
        return _to_wav(samples, sr)


class PiperTTS:
    name = "piper"

    def __init__(self) -> None:
        self._voices: dict[str, "PiperVoice"] = {}

    def _paths(self, lang: str):
        voice = PIPER_VOICES[lang]
        base = config.PIPER_DIR / lang / voice
        return base.with_suffix(".onnx"), base.with_suffix(".onnx.json")

    def available(self) -> bool:
        return PIPER_INSTALLED

    def supports(self, lang: str) -> bool:
        return lang in PIPER_VOICES and all(p.exists() for p in self._paths(lang))

    def synthesize(self, text: str, lang: str, speed: float = 1.0) -> bytes:
        if lang not in self._voices:
            onnx, cfg = self._paths(lang)
            self._voices[lang] = PiperVoice.load(str(onnx), config_path=str(cfg), use_cuda=False)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            self._voices[lang].synthesize_wav(text, wav)
        return buf.getvalue()


ENGINES = {e.name: e for e in (KokoroTTS(), PiperTTS())}


def status() -> dict[str, bool]:
    return {name: eng.available() for name, eng in ENGINES.items()}


def synthesize(text: str, lang: str, speed: float = 1.0) -> tuple[bytes, str]:
    """Retorna (wav_bytes, motor_usado). Lança RuntimeError se nenhum motor servir."""
    text = clean_for_speech(text, lang)
    if not text:
        raise RuntimeError("Texto vazio após limpeza.")
    errors = []
    for name in config.TTS_ORDER:
        eng = ENGINES.get(name)
        if eng is None or not eng.available() or not eng.supports(lang):
            continue
        try:
            return eng.synthesize(text, lang, speed), name
        except Exception as exc:
            log.warning("TTS %s falhou: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise RuntimeError(
        "Nenhum motor de voz disponível para este idioma. "
        "Execute: python download_models.py --kokoro. " + " | ".join(errors)
    )
