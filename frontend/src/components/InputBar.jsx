// src/components/InputBar.jsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp, Mic, MicOff, Loader2, AlertCircle, Map, PenLine, Stethoscope, Library, Headphones, PhoneOff, AudioLines } from 'lucide-react'
import { useVoice } from '../hooks/useVoiceMode'

const VOICE_STATUS = {
  loading:      { text: 'Carregando detector de voz…',            dot: 'bg-neutral-400' },
  listening:    { text: 'Ouvindo — pode falar',                   dot: 'bg-emerald-500 animate-pulse' },
  userSpeaking: { text: 'Você está falando…',                     dot: 'bg-emerald-500 animate-ping' },
  transcribing: { text: 'Transcrevendo…',                         dot: 'bg-sky-500 animate-pulse' },
  thinking:     { text: 'Pensando…',                              dot: 'bg-amber-500 animate-pulse' },
  speaking:     { text: 'Tutor falando…',                         dot: 'bg-violet-500 animate-pulse' },
}

const QUICK_ACTIONS = [
  { id: 'roadmap',   label: 'Roadmap',     icon: Map,         hint: 'Plano de estudo baseado nos livros e no seu domínio' },
  { id: 'exercise',  label: 'Exercício',   icon: PenLine,     hint: 'Exercício do livro (escreva um tema antes para direcionar)' },
  { id: 'diagnosis', label: 'Diagnóstico', icon: Stethoscope, hint: 'No que você precisa melhorar' },
]
import { useApp, LANGUAGES } from '../context/AppContext'
import { useChat } from '../hooks/useChat'
import { useAudioRecorder } from '../hooks/useAudioRecorder'
import { transcribeAudio } from '../lib/api'

export default function InputBar() {
  const { isStreaming, settings, currentSession, createSession, health, backendOnline, setLibraryOpen, setPronunciation } = useApp()
  const { sendMessage } = useChat()
  const voice = useVoice()
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

  // ── Ações rápidas (roadmap, exercício, diagnóstico) ─────
  const runAction = useCallback(async (action, label) => {
    if (isStreaming || !backendOnline) return
    const extra = text.trim()
    setText('')
    if (!currentSession) await createSession()
    sendMessage(extra ? `${label}: ${extra}` : label, action)
  }, [isStreaming, backendOnline, text, currentSession, createSession, sendMessage])

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

  if (voice.active && !voice.showText) return null

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

        {/* Modo conversa por voz */}
        {voice.active && (
          <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-xl bg-neutral-50 border border-neutral-200 text-xs text-neutral-700">
            <span className={`w-2 h-2 rounded-full ${VOICE_STATUS[voice.state]?.dot}`} />
            <span className="font-medium">{VOICE_STATUS[voice.state]?.text}</span>
            {voice.latency != null && (
              <span className="text-neutral-400" title="Do fim da sua fala até o início da resposta falada">
                · resposta em {(voice.latency / 1000).toFixed(1)} s
              </span>
            )}
            {(voice.state === 'speaking' || voice.state === 'thinking') && (
              <button onClick={voice.interrupt}
                      className="ml-auto px-2 py-1 rounded-lg text-neutral-600 hover:bg-neutral-100">
                Interromper
              </button>
            )}
            <button onClick={() => voice.setShowText(false)}
                    className={`${voice.state === 'speaking' || voice.state === 'thinking' ? '' : 'ml-auto '}px-2 py-1 rounded-lg text-neutral-600 hover:bg-neutral-100`}>
              Voltar ao modo voz
            </button>
            <button onClick={voice.stop}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-red-600 hover:bg-red-50">
              <PhoneOff className="w-3 h-3" /> Encerrar
            </button>
          </div>
        )}
        {voice.error && (
          <div className="flex items-center gap-2 mb-2 text-xs text-red-500">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" /> <span>{voice.error}</span>
          </div>
        )}

        {/* Ações rápidas */}
        <div className="flex flex-wrap items-center gap-1.5 mb-2">
          {QUICK_ACTIONS.map(a => (
            <button
              key={a.id}
              onClick={() => runAction(a.id, a.label)}
              disabled={isStreaming || !backendOnline}
              title={a.hint}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-neutral-600 border border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300 disabled:opacity-40 transition-all"
            >
              <a.icon className="w-3 h-3" /> {a.label}
            </button>
          ))}
          {langInfo?.kind === 'language' && health.pronunciation && (
            <button
              onClick={() => setPronunciation({ text: '' })}
              title="Treine sons difíceis para brasileiros, com nota por som"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-neutral-600 border border-neutral-200 hover:bg-neutral-50 hover:border-neutral-300 transition-all"
            >
              <AudioLines className="w-3 h-3" /> Pronúncia
            </button>
          )}
          <button
            onClick={() => setLibraryOpen(true)}
            className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-neutral-500 hover:text-neutral-800 hover:bg-neutral-50 transition-all"
          >
            <Library className="w-3 h-3" />
            {settings.bookIds.length > 0
              ? `${settings.bookIds.length} livro${settings.bookIds.length > 1 ? 's' : ''} como base`
              : 'Usar livros'}
          </button>
        </div>

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

          {/* Modo conversa (voz contínua) */}
          {langHasSTT && !voice.active && (
            <button
              onClick={voice.start}
              disabled={isStreaming || isRecording}
              title="Modo conversa: fale naturalmente, sem apertar botões"
              className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 transition-all"
            >
              <Headphones className="w-4 h-4" />
            </button>
          )}

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
