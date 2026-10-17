// src/components/MessageItem.jsx
import { useState, useCallback } from 'react'
import { ChevronDown, Volume2, Loader2, User, Bot, BookOpen, CheckCircle2 } from 'lucide-react'
import { LANGUAGES, useApp } from '../context/AppContext'
import { fetchTTS } from '../lib/api'
import Markdown, { visiblePart } from './Markdown'

export default function MessageItem({ message }) {
  const { settings } = useApp()
  const { role, content, feedback, streaming, isError, provider, citations, verified } = message
  const [citesOpen, setCitesOpen] = useState(false)

  const [feedbackOpen, setFeedbackOpen]   = useState(false)
  const [ttsLoading, setTtsLoading]       = useState(false)
  const [audioUrl, setAudioUrl]           = useState(null)
  const [ttsError, setTtsError]           = useState(null)
  const isUser      = role === 'user'
  const langHasTTS  = LANGUAGES[settings.language]?.tts ?? false

  const handleTTS = useCallback(async () => {
    if (ttsLoading) return
    setTtsError(null)

    if (audioUrl) {
      new Audio(audioUrl).play()
      return
    }

    setTtsLoading(true)
    try {
      const url = await fetchTTS(content, settings.language)
      setAudioUrl(url)
      new Audio(url).play()
    } catch (err) {
      setTtsError(err.message)
    } finally {
      setTtsLoading(false)
    }
  }, [ttsLoading, audioUrl, content, settings.language])

  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[78%] flex items-end gap-2">
          <div className="bg-neutral-100 rounded-2xl rounded-br-sm px-4 py-3">
            <p className="text-sm text-neutral-900 message-content">{content}</p>
          </div>
          <div className="w-7 h-7 rounded-full bg-neutral-200 flex items-center justify-center shrink-0 mb-0.5">
            <User className="w-3.5 h-3.5 text-neutral-500" />
          </div>
        </div>
      </div>
    )
  }

  // Mensagem do assistente
  return (
    <div className="flex items-start gap-3 animate-fade-in">
      {/* Avatar */}
      <div className="w-7 h-7 rounded-full bg-neutral-900 flex items-center justify-center shrink-0 mt-0.5">
        <Bot className="w-3.5 h-3.5 text-white" />
      </div>

      <div className="flex-1 min-w-0 max-w-[85%]">
        {/* Conteúdo da mensagem */}
        <div className={`relative ${isError ? 'text-red-500' : 'text-neutral-900'}`}>
          {isError
            ? <p className="text-sm leading-relaxed message-content">{content}</p>
            : <div className={`text-sm leading-relaxed ${streaming && content ? 'streaming-cursor' : ''}`}>
                <Markdown>{visiblePart(content) || (streaming ? '' : '…')}</Markdown>
              </div>}
          {streaming && !content && (
            <span className="inline-flex gap-1 mt-1">
              <span className="w-1.5 h-1.5 bg-neutral-300 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 bg-neutral-300 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 bg-neutral-300 rounded-full animate-bounce [animation-delay:300ms]" />
            </span>
          )}
        </div>

        {/* Ações: TTS + Feedback (só após streaming terminar) */}
        {!streaming && !isError && (
          <div className="mt-2 flex flex-col gap-1.5">
            {/* Linha de ações */}
            <div className="flex items-center gap-2">
              {/* Botão TTS */}
              {langHasTTS && (
                <button
                  onClick={handleTTS}
                  disabled={ttsLoading}
                  title="Ouvir resposta"
                  className="
                    flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                    text-xs text-neutral-400 border border-neutral-200
                    hover:text-neutral-700 hover:border-neutral-300 hover:bg-neutral-50
                    disabled:opacity-50 transition-all
                  "
                >
                  {ttsLoading
                    ? <Loader2 className="w-3 h-3 animate-spin" />
                    : <Volume2 className="w-3 h-3" />
                  }
                  Ouvir
                </button>
              )}

              {/* Botão Feedback */}
              {feedback && (
                <button
                  onClick={() => setFeedbackOpen(o => !o)}
                  className="
                    flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                    text-xs text-neutral-400 border border-neutral-200
                    hover:text-neutral-700 hover:border-neutral-300 hover:bg-neutral-50
                    transition-all
                  "
                >
                  <ChevronDown className={`w-3 h-3 transition-transform duration-150 ${feedbackOpen ? 'rotate-180' : ''}`} />
                  Feedback
                </button>
              )}
              {citations?.length > 0 && (
                <button
                  onClick={() => setCitesOpen(o => !o)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-neutral-400 border border-neutral-200 hover:text-neutral-700 hover:border-neutral-300 hover:bg-neutral-50 transition-all"
                >
                  <BookOpen className="w-3 h-3" />
                  {citations.length} fonte{citations.length > 1 ? 's' : ''}
                </button>
              )}

              {verified && (
                <span title="O gabarito deste exercício foi calculado pelo SymPy e será usado na correção"
                      className="flex items-center gap-1 text-xs text-emerald-600">
                  <CheckCircle2 className="w-3 h-3" /> gabarito verificado
                </span>
              )}

              {provider && (
                <span className="ml-auto text-[11px] text-neutral-300" title="Provedor que gerou a resposta">
                  {provider}
                </span>
              )}
            </div>

            {/* Citações */}
            {citesOpen && citations?.length > 0 && (
              <div className="animate-slide-up space-y-1.5">
                {citations.map(c => (
                  <div key={c.n} className="bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2">
                    <p className="text-xs font-medium text-neutral-700">
                      [{c.n}] {c.book} — p. {c.page_start}{c.page_end !== c.page_start ? `–${c.page_end}` : ''}
                      {c.kind === 'exercise' && <span className="ml-1.5 text-amber-600">· exercício</span>}
                    </p>
                    {c.section && <p className="text-[11px] text-neutral-400 truncate">{c.section}</p>}
                    <p className="text-xs text-neutral-500 mt-1 line-clamp-3">{c.snippet}</p>
                  </div>
                ))}
              </div>
            )}

            {/* TTS Error */}
            {ttsError && (
              <p className="text-xs text-red-400">{ttsError}</p>
            )}

            {/* Feedback accordion */}
            {feedback && feedbackOpen && (
              <div className="animate-slide-up bg-amber-50 border border-amber-100 rounded-xl px-3.5 py-3">
                <p className="text-xs font-medium text-amber-700 mb-1">📚 Feedback Pedagógico</p>
                <div className="text-sm text-amber-800 leading-relaxed"><Markdown>{feedback}</Markdown></div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
