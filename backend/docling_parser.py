"""
docling_parser.py — Extração de alta fidelidade com IBM Docling (fórmulas em LaTeX, tabelas).

Usado nos livros marcados como "alta fidelidade". Comparado ao PyMuPDF4LLM (medido no livro
Mathematics for Machine Learning, p. 112–117):
  • fórmulas em destaque saem como LaTeX ($$ A = \\left[\\begin{matrix} 4 & 2 \\\\ 1 & 3 \\end{matrix}\\right] $$)
    em vez de texto quebrado;
  • custo: ~7 s/página na RTX 4050 (o PyMuPDF faz ~1 s/página).
Matemática no meio de frases continua como texto (o Docling só converte fórmulas em destaque).

As páginas são processadas em lotes para reportar progresso e limitar memória.
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Callable, Optional

from model_lock import LOAD_LOCK

log = logging.getLogger("tutor.docling")

BATCH_PAGES = 15


def available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def _converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # Sem o modelo de fórmulas o Docling marca equações como "não decodificadas" (pior que o PyMuPDF)
    opts = PdfPipelineOptions(do_ocr=False, do_formula_enrichment=True, do_table_structure=True)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def _item_markdown(item, doc) -> str:
    label = item.label.value
    text = (getattr(item, "text", "") or "").strip()
    if label == "formula":
        return f"$$\n{text}\n$$" if text else ""
    if label == "table":
        try:
            return item.export_to_markdown(doc)
        except Exception:
            return text
    if label == "code":
        return f"```\n{text}\n```" if text else ""
    if label in ("section_header", "title"):
        return f"## {text}" if text else ""
    if label == "list_item":
        return f"- {text}" if text else ""
    if label in ("page_header", "page_footer"):
        return ""   # cabeçalhos/rodapés repetidos só poluem a busca
    return text


def extract_pages(path: Path, total_pages: int,
                  on_progress: Optional[Callable[[float], None]] = None) -> list[tuple[int, str]]:
    """[(nº da página, markdown com fórmulas em $$LaTeX$$)] para o livro inteiro."""
    conv = _converter()
    pages: dict[int, list[str]] = {}
    try:
        for start in range(1, total_pages + 1, BATCH_PAGES):
            end = min(total_pages, start + BATCH_PAGES - 1)
            if start == 1:
                # O 1º lote carrega os modelos do Docling: não pode coincidir com outra carga
                with LOAD_LOCK:
                    res = conv.convert(str(path), page_range=(start, end), raises_on_error=False)
            else:
                res = conv.convert(str(path), page_range=(start, end), raises_on_error=False)
            doc = res.document
            for item, _level in doc.iterate_items():
                prov = getattr(item, "prov", None)
                if not prov:
                    continue
                md = _item_markdown(item, doc)
                if md:
                    pages.setdefault(prov[0].page_no, []).append(md)
            if on_progress:
                on_progress(end / total_pages)
    finally:
        del conv
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()   # devolve a VRAM ao Whisper/reranker
        except Exception:
            pass
    return [(n, "\n\n".join(pages.get(n, []))) for n in range(1, total_pages + 1)]
