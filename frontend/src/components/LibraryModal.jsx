// src/components/LibraryModal.jsx
// Biblioteca: envio de PDFs, acompanhamento da importação e escolha dos livros usados como base.
import { useCallback, useEffect, useRef, useState } from 'react'
import { X, Upload, Trash2, RotateCcw, Loader2, BookOpen, CheckSquare, Square, Sigma } from 'lucide-react'
import { DOMAINS, useApp } from '../context/AppContext'
import * as api from '../lib/api'

const STATUS = {
  queued:     { label: 'Na fila',       cls: 'text-neutral-500' },
  processing: { label: 'Processando',   cls: 'text-amber-600' },
  ready:      { label: 'Pronto',        cls: 'text-emerald-600' },
  error:      { label: 'Erro',          cls: 'text-red-500' },
}

export default function LibraryModal() {
  const { libraryOpen, setLibraryOpen, settings, setBookIds, currentSession, health } = useApp()
  const [books, setBooks]       = useState([])
  const [uploading, setUploading] = useState(false)
  const [error, setError]       = useState(null)
  // Alta fidelidade (Docling): fórmulas em LaTeX; ligado por padrão em domínios técnicos
  const [hiFi, setHiFi]         = useState(DOMAINS[settings.language]?.kind === 'tech')
  const fileRef = useRef(null)

  const refresh = useCallback(() => api.getBooks().then(setBooks), [])

  // Atualiza a cada 3 s enquanto houver livro sendo importado
  useEffect(() => {
    if (!libraryOpen) return
    refresh()
    const busy = books.some(b => b.status === 'queued' || b.status === 'processing')
    if (!busy) return
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [libraryOpen, refresh, books.map(b => b.status + b.progress).join()])

  if (!libraryOpen) return null

  async function handleFiles(files) {
    setError(null)
    setUploading(true)
    try {
      for (const file of files) await api.uploadBook(file, settings.language, hiFi && health.docling ? 'docling' : 'fast')
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function toggle(id) {
    const ids = settings.bookIds.includes(id)
      ? settings.bookIds.filter(x => x !== id)
      : [...settings.bookIds, id]
    setBookIds(ids)
  }

  async function remove(id) {
    if (!confirm('Remover este livro da biblioteca?')) return
    await api.deleteBook(id)
    if (settings.bookIds.includes(id)) setBookIds(settings.bookIds.filter(x => x !== id))
    refresh()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in"
      onClick={() => setLibraryOpen(false)}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 p-6 animate-slide-up max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-base font-semibold text-neutral-900">Biblioteca</h2>
          <button onClick={() => setLibraryOpen(false)}
                  className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="text-xs text-neutral-500 mb-4">
          Marque os livros que o tutor deve usar como base
          {currentSession ? ' nesta conversa' : ' nas próximas conversas'}.
          Respostas citam livro e página.
        </p>

        {/* Upload */}
        <label
          className={`flex flex-col items-center justify-center gap-1 border-2 border-dashed rounded-xl py-5 cursor-pointer transition-colors
            ${uploading ? 'border-neutral-200 bg-neutral-50' : 'border-neutral-300 hover:border-neutral-500 hover:bg-neutral-50'}`}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); handleFiles([...e.dataTransfer.files]) }}
        >
          {uploading ? <Loader2 className="w-5 h-5 text-neutral-400 animate-spin" />
                     : <Upload className="w-5 h-5 text-neutral-400" />}
          <span className="text-sm text-neutral-600">
            {uploading ? 'Enviando…' : 'Arraste PDFs aqui ou clique para escolher'}
          </span>
          <span className="text-[11px] text-neutral-400">
            Importação leva alguns minutos (≈ 1 min a cada 50 páginas)
          </span>
          <input ref={fileRef} type="file" accept="application/pdf" multiple className="hidden"
                 disabled={uploading} onChange={e => handleFiles([...e.target.files])} />
        </label>
        {health.docling && (
          <label className="mt-2 flex items-start gap-2 text-xs text-neutral-600 cursor-pointer">
            <input type="checkbox" checked={hiFi} onChange={e => setHiFi(e.target.checked)} className="mt-0.5 accent-neutral-900" />
            <span>
              <span className="font-medium text-neutral-800">Alta fidelidade</span> — fórmulas viram LaTeX (Docling).
              Recomendado para livros de matemática; ~7 s por página (um livro de 400 páginas leva ~45 min).
            </span>
          </label>
        )}
        {error && <p className="mt-2 text-xs text-red-500">{error}</p>}

        {/* Lista */}
        <div className="mt-4 flex-1 overflow-y-auto space-y-2">
          {books.length === 0 && (
            <p className="text-xs text-neutral-400 text-center py-6">Nenhum livro ainda.</p>
          )}
          {books.map(b => {
            const st = STATUS[b.status] ?? STATUS.queued
            const selected = settings.bookIds.includes(b.id)
            const ready = b.status === 'ready'
            return (
              <div key={b.id} className={`group flex items-start gap-3 rounded-xl border px-3 py-2.5
                    ${selected ? 'border-neutral-900 bg-neutral-50' : 'border-neutral-200'}`}>
                <button onClick={() => ready && toggle(b.id)} disabled={!ready}
                        title={ready ? 'Usar como base' : 'Aguarde a importação'}
                        className="mt-0.5 text-neutral-700 disabled:text-neutral-300">
                  {selected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-neutral-900 truncate flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5 text-neutral-400 shrink-0" /> {b.title}
                  </p>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    <span className={st.cls}>{st.label}</span>
                    {b.pages > 0 && ` · ${b.pages} páginas`}
                    {b.parser === 'docling' && <span className="text-violet-600"> · alta fidelidade</span>}
                    {DOMAINS[b.domain] && ` · ${DOMAINS[b.domain].flag} ${DOMAINS[b.domain].label}`}
                  </p>
                  {(b.status === 'processing' || b.status === 'queued') && (
                    <div className="mt-1.5 h-1 bg-neutral-100 rounded-full overflow-hidden">
                      <div className="h-full bg-amber-400 transition-all" style={{ width: `${Math.round(b.progress * 100)}%` }} />
                    </div>
                  )}
                  {b.status === 'error' && <p className="mt-1 text-xs text-red-500 line-clamp-2">{b.error}</p>}
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {b.status === 'error' && (
                    <button onClick={async () => { await api.retryBook(b.id); refresh() }} title="Tentar de novo"
                            className="p-1 text-neutral-400 hover:text-neutral-700"><RotateCcw className="w-3.5 h-3.5" /></button>
                  )}
                  {ready && b.parser !== 'docling' && health.docling && (
                    <button onClick={async () => { await api.retryBook(b.id, 'docling'); refresh() }}
                            title="Reprocessar em alta fidelidade (fórmulas em LaTeX)"
                            className="p-1 text-neutral-400 hover:text-violet-600"><Sigma className="w-3.5 h-3.5" /></button>
                  )}
                  <button onClick={() => remove(b.id)} title="Remover"
                          className="p-1 text-neutral-300 hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
