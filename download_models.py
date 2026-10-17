"""
download_models.py
==================
Script para pré-download e verificação dos modelos Piper TTS offline.

Uso:
    python download_models.py                   # baixa todos os idiomas padrão
    python download_models.py --lang es         # baixa apenas Espanhol
    python download_models.py --check           # apenas verifica modelos existentes

Os modelos são salvos em: ./models/piper/<lang>/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Configuração dos modelos por idioma
# Fonte: https://github.com/rhasspy/piper/blob/master/VOICES.md
# ---------------------------------------------------------------------------
MODELS_CONFIG: Dict[str, Dict[str, str]] = {
    "es": {
        "name": "Espanhol",
        "voice": "es_ES-davefx-medium",
        "onnx_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx"
        ),
        "json_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json"
        ),
    },
    "en": {
        "name": "Inglês",
        "voice": "en_US-lessac-medium",
        "onnx_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
        ),
        "json_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
        ),
    },
    "it": {
        "name": "Italiano",
        "voice": "it_IT-riccardo-x_low",
        "onnx_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx"
        ),
        "json_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx.json"
        ),
    },
    "ru": {
        "name": "Russo",
        "voice": "ru_RU-denis-medium",
        "onnx_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx"
        ),
        "json_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx.json"
        ),
    },
    "fr": {
        "name": "Francês",
        "voice": "fr_FR-upmc-medium",
        "onnx_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx"
        ),
        "json_url": (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            "/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx.json"
        ),
    },
    # Chinês (“zh”): Piper TTS não possui voz em mandarim disponível.
    # O app opera em modo texto (caracteres + pinyin) para este idioma.
}

MODELS_DIR = Path(__file__).parent / "models" / "piper"

# Kokoro TTS (voz principal, mais natural) — github.com/thewh1teagle/kokoro-onnx
KOKORO_DIR = Path(__file__).parent / "models" / "kokoro"
KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    """Callback de progresso para urllib.request.urlretrieve."""
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(downloaded / total_size * 100, 100)
        bar = "█" * int(pct // 2) + "░" * (50 - int(pct // 2))
        mb_done = downloaded / 1_048_576
        mb_total = total_size / 1_048_576
        print(
            f"\r  [{bar}] {pct:5.1f}%  {mb_done:.1f}/{mb_total:.1f} MB",
            end="",
            flush=True,
        )
    else:
        mb = block_num * block_size / 1_048_576
        print(f"\r  Baixando… {mb:.1f} MB", end="", flush=True)


def _download_file(url: str, dest: Path) -> None:
    """Baixa `url` para `dest` exibindo progresso."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↳ {dest.name}")
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress_hook)
        print()  # nova linha após barra de progresso
    except Exception as exc:  # noqa: BLE001
        print(f"\n  [ERRO] Falha ao baixar {url}: {exc}")
        raise


def get_model_paths(lang_code: str) -> Tuple[Path, Path]:
    """Retorna (caminho_onnx, caminho_json) para um código de idioma."""
    cfg = MODELS_CONFIG[lang_code]
    base = MODELS_DIR / lang_code / cfg["voice"]
    return base.with_suffix(".onnx"), Path(str(base) + ".onnx.json")


def model_exists(lang_code: str) -> bool:
    """Verifica se ambos os arquivos do modelo existem no disco."""
    onnx_path, json_path = get_model_paths(lang_code)
    return onnx_path.exists() and json_path.exists()


# ---------------------------------------------------------------------------
# Operações principais
# ---------------------------------------------------------------------------

def check_all() -> None:
    """Exibe o status de cada modelo no disco."""
    print("\n📋  Status dos modelos Piper TTS:")
    print(f"   Diretório: {MODELS_DIR.resolve()}\n")
    for code, cfg in MODELS_CONFIG.items():
        status = "✅ Instalado" if model_exists(code) else "❌ Ausente"
        print(f"   [{code}] {cfg['name']:10s}  →  {status}")
    print()


def download_lang(lang_code: str) -> None:
    """Baixa os arquivos .onnx e .onnx.json para o idioma informado."""
    if lang_code not in MODELS_CONFIG:
        print(f"[ERRO] Código de idioma desconhecido: '{lang_code}'")
        print(f"       Opções válidas: {', '.join(MODELS_CONFIG)}")
        sys.exit(1)

    cfg = MODELS_CONFIG[lang_code]
    onnx_path, json_path = get_model_paths(lang_code)

    print(f"\n🔊  Modelo: {cfg['name']}  ({cfg['voice']})")

    if onnx_path.exists():
        print(f"  ✅ .onnx já existe → pulando ({onnx_path.name})")
    else:
        _download_file(cfg["onnx_url"], onnx_path)

    if json_path.exists():
        print(f"  ✅ .onnx.json já existe → pulando ({json_path.name})")
    else:
        _download_file(cfg["json_url"], json_path)

    print(f"  ✅ {cfg['name']} pronto!\n")


def download_kokoro() -> None:
    """Baixa o modelo Kokoro (fp32, ~310 MB — mais rápido que o int8 na CPU) e o pacote de vozes (~27 MB)."""
    print("\n🔊  Kokoro TTS")
    for name in KOKORO_FILES:
        dest = KOKORO_DIR / name
        if dest.exists():
            print(f"  ✅ {name} já existe → pulando")
        else:
            _download_file(f"{KOKORO_BASE}/{name}", dest)
    print("  ✅ Kokoro pronto!\n")


def download_all() -> None:
    """Baixa modelos para todos os idiomas configurados."""
    print("🚀  Iniciando download de todos os modelos Piper TTS…")
    for code in MODELS_CONFIG:
        download_lang(code)
    download_kokoro()
    print("🎉  Todos os modelos foram baixados com sucesso!")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gerenciador de modelos Piper TTS para o app de idiomas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--lang",
        metavar="CÓDIGO",
        choices=list(MODELS_CONFIG.keys()),
        help="Baixa apenas o idioma especificado (ex: es, en, it, ru).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Apenas verifica quais modelos estão instalados.",
    )
    parser.add_argument(
        "--kokoro",
        action="store_true",
        help="Baixa apenas o Kokoro TTS (voz principal).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.check:
        check_all()
        for name in KOKORO_FILES:
            ok = "✅ Instalado" if (KOKORO_DIR / name).exists() else "❌ Ausente"
            print(f"   [kokoro] {name:24s}  →  {ok}")
    elif args.kokoro:
        download_kokoro()
    elif args.lang:
        download_lang(args.lang)
    else:
        download_all()


if __name__ == "__main__":
    main()
