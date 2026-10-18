// src/components/PdfPanel.jsx
// Painel lateral com o PDF do livro: abre na página citada e destaca o trecho da citação.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Loader2 } from 'lucide-react'
import { useApp } from '../context/AppContext'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

const escapeHtml = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

const norm = s => s.toLowerCase().normalize('NFKD').replace(/[^\p{L}\p{N}]+/gu, ' ').trim()

// Palavras "fortes" do trecho citado (o texto extraído e o do PDF nem sempre batem 1:1)
function snippetWords(snippet) {
  return new Set(norm(snippet ?? '').split(' ').filter(w => w.length >= 4))
}

export default function PdfPanel() {
  const { pdfView, setPdfView, setSidebarOpen } = useApp()
  const [numPages, setNumPages] = useState(null)
  const [page, setPage] = useState(1)
  const [scale, setScale] = useState(1.0)
  const [width, setWidth] = useState(520)
  const boxRef = useRef(null)

  // Nova citação: vai para a página dela
  useEffect(() => { if (pdfView) setPage(pdfView.page || 1) }, [pdfView])

  // Abre espaço para chat + livro: recolhe a barra lateral e a restaura ao fechar
  const isOpen = Boolean(pdfView)
  useEffect(() => {
    if (!isOpen) return
    let previous
    setSidebarOpen(prev => { previous = prev; return false })
    return () => setSidebarOpen(previous ?? true)
  }, [isOpen, setSidebarOpen])

  // Página ocupa a largura do painel
  useEffect(() => {
    if (!boxRef.current) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width - 24)))
    ro.observe(boxRef.current)
    return () => ro.disconnect()
  }, [pdfView])

  const words = useMemo(() => snippetWords(pdfView?.snippet), [pdfView])
  const onCitedPage = pdfView && page >= pdfView.page && page <= (pdfView.pageEnd ?? pdfView.page)

  // Destaca itens de texto da página cujas palavras aparecem no trecho citado
  const textRenderer = useMemo(() => ({ str }) => {
    if (!onCitedPage || words.size === 0) return escapeHtml(str)
    const ws = norm(str).split(' ').filter(w => w.length >= 4)
    const hits = ws.filter(w => words.has(w)).length
    // customTextRenderer devolve HTML: o texto do PDF precisa ser escapado
    return ws.length > 0 && hits / ws.length >= 0.6 ? `<mark class="pdf-hit">${escapeHtml(str)}</mark>` : escapeHtml(str)
  }, [words, onCitedPage])

  if (!pdfView) return null
  const go = d => setPage(p => Math.min(numPages ?? p, Math.max(1, p + d)))

  return (
    <aside className="w-[46%] min-w-[340px] max-w-[760px] h-full border-l border-neutral-200 flex flex-col bg-neutral-50">
      <header className="flex items-center gap-2 px-3 py-2 border-b border-neutral-200 bg-white">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-neutral-900 truncate">{pdfView.title}</p>
          {pdfView.section && <p className="text-[11px] text-neutral-400 truncate">{pdfView.section}</p>}
        </div>
        <button onClick={() => setScale(s => Math.max(0.6, s - 0.15))} title="Diminuir"
                className="p-1.5 rounded-lg text-neutral-500 hover:bg-neutral-100"><ZoomOut className="w-4 h-4" /></button>
        <button onClick={() => setScale(s => Math.min(2.2, s + 0.15))} title="Aumentar"
                className="p-1.5 rounded-lg text-neutral-500 hover:bg-neutral-100"><ZoomIn className="w-4 h-4" /></button>
        <button onClick={() => setPdfView(null)} title="Fechar"
                className="p-1.5 rounded-lg text-neutral-500 hover:bg-neutral-100"><X className="w-4 h-4" /></button>
      </header>

      <div ref={boxRef} className="flex-1 overflow-auto px-3 py-3">
        <Document
          file={`/api/books/${pdfView.bookId}/file`}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
          loading={<div className="flex justify-center py-10 text-neutral-400"><Loader2 className="w-5 h-5 animate-spin" /></div>}
          error={<p className="text-sm text-red-500 p-4">Não foi possível abrir o PDF.</p>}
        >
          <Page pageNumber={page} width={width * scale} customTextRenderer={textRenderer}
                renderAnnotationLayer={false} className="shadow-sm mx-auto" />
        </Document>
      </div>

      <footer className="flex items-center justify-center gap-3 px-3 py-2 border-t border-neutral-200 bg-white text-sm">
        <button onClick={() => go(-1)} disabled={page <= 1}
                className="p-1 rounded-lg text-neutral-500 hover:bg-neutral-100 disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
        <span className="tabular-nums text-neutral-600">
          página {page}{numPages ? ` de ${numPages}` : ''}
          {onCitedPage && <span className="ml-2 text-amber-600">· trecho citado</span>}
        </span>
        <button onClick={() => go(1)} disabled={numPages != null && page >= numPages}
                className="p-1 rounded-lg text-neutral-500 hover:bg-neutral-100 disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
      </footer>
    </aside>
  )
}
