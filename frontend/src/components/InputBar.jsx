// src/components/InputBar.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp, Mic, MicOff, Loader2, AlertCircle } from 'lucide-react'
import { useApp, LANGUAGES } from '../context/AppContext'
import { useChat } from '../hooks/useChat'
import { useAudioRecorder } from '../hooks/useAudioRecorder'
import { transcribeAudio } from '../lib/api'

export default function InputBar() {
  const { isStreaming, settings, currentSession, createSession, health, backendOnline } = useApp()
  const { sendMessage } = useChat()
  const {
    isRecording, audioBlob, durationSec, error: recError,
    startRecording, stopRecording, reset: resetRecorder,
  } = useAudioRecorder()

  const [text, setText]           = useState('')
  const [transcribing, setTranscribing] = useState(false)
  const [sttError, setSttError]   = useState(null)
  const textareaRef = useRef(null)

  const canSend = text.trim().length > 0 && !isStreaming && backendOnline
  const langHasSTT = health.whisper && backendOnline

  // ── Auto-resize do textarea ─────────────────────────────
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }, [text])

  // ── Foca o textarea quando o streaming termina ──────────
  useEffect(() => {
    if (!isStreaming) textareaRef.current?.focus()
  }, [isStreaming])

  // ── Transcreve quando parar de gravar ──────────────────
  useEffect(() => {
    if (!audioBlob) return
    ;(async () => {
      setSttError(null)
      setTranscribing(true)
      try {
        const { transcript } = await transcribeAudio(audioBlob, settings.language)
        if (transcript) {
          setText(t => t ? `${t} ${transcript}` : transcript)
          textareaRef.current?.focus()
        }
      } catch (err) {
        setSttError(err.message)
      } finally {
        setTranscribing(false)
        resetRecorder()
      }
    })()
  }, [audioBlob])

  // ── Envio ───────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    if (!canSend) return
    const msg = text.trim()
    setText('')

    // Garante que há uma sessão ativa
    if (!currentSession) await createSession()

    sendMessage(msg)
  }, [canSend, text, currentSession, createSession, sendMessage])

  // ── Teclas ──────────────────────────────────────────────
  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── Microfone ───────────────────────────────────────────
  function handleMic() {
    if (isRecording) {
      stopRecording()
    } else {
      setSttError(null)
      startRecording()
    }
  }

  const langInfo = LANGUAGES[settings.language]

  return (
    <div className="border-t border-neutral-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto">
        {/* Banner: backend offline */}
        {!backendOnline && (
          <div className="flex items-start gap-2 mb-2 px-3 py-2.5 bg-red-50 border border-red-100 rounded-xl text-xs text-red-700">
            <span className="shrink-0 mt-0.5">🔴</span>
            <div>
              <span className="font-medium">Backend offline.</span> Inicie o servidor e aguarde reconexão automática:
              <code className="block mt-1 font-mono bg-red-100 rounded px-2 py-1 text-red-800 select-all">
                .\start_backend.ps1
              </code>
            </div>
          </div>
        )}

        {(recError || sttError) && (
          <div className="flex items-center gap-2 mb-2 text-xs text-red-500">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>{recError || sttError}</span>
          </div>
        )}

        {/* Status de gravação */}
        {isRecording && (
          <div className="flex items-center gap-2 mb-2 text-xs text-red-500 animate-pulse">
            <span className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
            Gravando… {durationSec}s — clique no microfone para parar
          </div>
        )}

        {/* Caixa de entrada */}
        <div className="flex items-end gap-2 bg-white border border-neutral-200 rounded-2xl px-3 py-2 shadow-sm focus-within:border-neutral-400 transition-colors">
          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming
                ? 'Aguardando resposta…'
                : langInfo?.kind === 'tech'
                  ? `Pergunte sobre ${langInfo.label}… (Enter para enviar, Shift+Enter para nova linha)`
                  : `Escreva em ${langInfo?.label ?? 'seu idioma'}… (Enter para enviar, Shift+Enter para nova linha)`
            }
            disabled={isStreaming}
            rows={1}
            className="
              flex-1 bg-transparent text-sm text-neutral-900 placeholder:text-neutral-400
              focus:outline-none leading-relaxed py-1 min-h-[36px] max-h-[200px]
              disabled:opacity-50 disabled:cursor-not-allowed
            "
          />

          {/* Botão microfone */}
          {langHasSTT && (
            <button
              onClick={handleMic}
              disabled={isStreaming || transcribing}
              title={isRecording ? 'Parar gravação' : 'Gravar áudio'}
              className={`
                shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all
                ${isRecording
                  ? 'bg-red-50 text-red-500 border border-red-200 animate-pulse'
                  : 'text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100'}
                disabled:opacity-40 disabled:cursor-not-allowed
              `}
            >
              {transcribing
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : isRecording
                  ? <MicOff className="w-4 h-4" />
                  : <Mic className="w-4 h-4" />
              }
            </button>
          )}

          {/* Botão enviar */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            title="Enviar (Enter)"
            className="
              shrink-0 w-9 h-9 rounded-xl flex items-center justify-center
              bg-neutral-900 text-white
              hover:bg-neutral-700
              disabled:opacity-30 disabled:cursor-not-allowed
              transition-all
            "
          >
            {isStreaming
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <ArrowUp className="w-4 h-4" />
            }
          </button>
        </div>

        {/* Dica */}
        <p className="text-center text-xs text-neutral-400 mt-2">
          {langInfo?.flag} {langInfo?.label} · {settings.level} · Whisper + Kokoro TTS
        </p>
      </div>
    </div>
  )
}
