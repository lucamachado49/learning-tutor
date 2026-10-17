"""
cuda_setup.py — Torna as DLLs do CUDA instaladas via pip visíveis no Windows.

O faster-whisper (CTranslate2) precisa de cuBLAS e cuDNN. Instalados pelos pacotes
nvidia-cublas-cu12 / nvidia-cudnn-cu12, eles ficam em site-packages/nvidia/*/bin,
fora do caminho de busca de DLLs. Importar este módulo antes do faster_whisper resolve.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def register_cuda_dlls() -> list[str]:
    if sys.platform != "win32":
        return []
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


register_cuda_dlls()
