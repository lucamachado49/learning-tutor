"""
cuda_setup.py — Garante UMA única cópia das DLLs do CUDA/cuDNN no processo (Windows).

O faster-whisper (CTranslate2) carrega cuBLAS/cuDNN pelo nome ("cudnn64_9.dll"), e o
Windows reaproveita a primeira DLL já carregada com esse nome. Misturar duas versões do
cuDNN no mesmo processo quebra um dos lados (símbolos ausentes, WinError 127).

  • Com PyTorch instalado (avaliação de pronúncia): importa o torch primeiro; ele carrega as
    próprias DLLs (torch/lib) e o Whisper passa a usar essas mesmas.
  • Sem PyTorch: usa as DLLs dos pacotes pip nvidia-cublas-cu12 / nvidia-cudnn-cu12.

Importar este módulo antes do faster_whisper.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("tutor.cuda")


def _use_torch_dlls() -> bool:
    try:
        import torch  # noqa: F401  (carrega torch/lib/*.dll)
    except ImportError:
        return False
    lib = Path(torch.__file__).parent / "lib"
    if lib.is_dir():
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
    return True


def _use_nvidia_pip_dlls() -> list[str]:
    added = []
    for site in map(Path, sys.path):
        nvidia = site / "nvidia"
        if not nvidia.is_dir():
            continue
        for bin_dir in nvidia.glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            # CTranslate2 carrega algumas DLLs via PATH, não via add_dll_directory
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            added.append(str(bin_dir))
    return added


def register_cuda_dlls() -> str:
    if sys.platform != "win32":
        return "n/a"
    if _use_torch_dlls():
        return "torch"
    _use_nvidia_pip_dlls()
    return "nvidia-pip"


SOURCE = register_cuda_dlls()
