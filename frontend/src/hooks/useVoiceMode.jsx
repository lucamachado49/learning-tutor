// src/hooks/useVoiceMode.js
// Modo conversa por voz: o VAD (Silero, no navegador) detecta quando você fala e quando para;
// a fala vai para o Whisper e a resposta do tutor é sintetizada FRASE A FRASE enquanto ainda é
// gerada.
//
// Eco: sem fone, o microfone capta a voz do tutor pelas caixas de som e o VAD acha que é você
// falando. Por isso, por padrão, o microfone PAUSA enquanto o tutor fala (interrompe-se tocando
// no círculo). Com fone, a opção "Interromper falando" mantém o microfone aberto (barge-in).

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
// O VAD (e o runtime ONNX) só é carregado ao ligar o modo voz
import { useApp, DOMAINS } from '../context/AppContext'
import { useChat } from './useChat'
import { transcribeAudio } from '../lib/api'
import { encodeWav, SentenceSplitter, SpeechQueue } from '../lib/speech'

const GREETING = {
  en: "I'm listening. Go ahead!",
  es: '¡Te escucho! Adelante.',
  tech: 'Pode falar, estou ouvindo.',
}

// off → loading → listening ⇄ userSpeaking → transcribing → thinking → speaking → listening
export function useVoiceMode() {
  const { settings } = useApp()
  const { sendMessage, stopStreaming } = useChat()

  const [state, setState]     = useState('off')
  const [error, setError]     = useState(null)
  const [latency, setLatency] = useState(null)   // ms do fim da fala até o 1º áudio
  const [caption, setCaption] = useState({ user: '', tutor: '' })

  const vadRef     = useRef(null)
  const queueRef   = useRef(null)
  const stateRef   = useRef('off')
  const turnRef    = useRef(0)       // invalida turnos antigos após interrupção
  const streamDone = useRef(true)
  const tSpeechEnd = useRef(0)
  const micPaused  = useRef(false)

  // Callbacks do VAD vivem muito tempo: leem sempre a versão mais recente via ref
  const latest = useRef({})
  latest.current = { sendMessage, stopStreaming, settings }

  const set = useCallback((s) => { stateRef.current = s; setState(s) }, [])

  // ── Microfone: pausa enquanto o tutor fala (a não ser que o barge-in esteja ligado) ──
  const pauseMic = useCallback(() => {
    if (latest.current.settings.voiceBargeIn || micPaused.current || !vadRef.current) return
    micPaused.current = true
    vadRef.current.pause()
  }, [])

  const resumeMic = useCallback(() => {
    if (!micPaused.current || !vadRef.current) return
    micPaused.current = false
    vadRef.current.start()
  }, [])

  const backToListening = useCallback(() => {
    if (stateRef.current === 'off') return
    resumeMic()
    set('listening')
  }, [set, resumeMic])

  // ── Interrompe o tutor (voz por cima, ou toque no círculo) ──
  const interrupt = useCallback((byVoice = false) => {
    const s = stateRef.current
    if (s === 'speaking' || s === 'thinking' || s === 'transcribing') {
      turnRef.current++
      queueRef.current?.stop()
      if (!streamDone.current) latest.current.stopStreaming()
      streamDone.current = true
      if (byVoice) set('userSpeaking')
      else backToListening()
    }
  }, [set, backToListening])

  const newQueue = useCallback(() => new SpeechQueue({
    onStart: () => {
      if (stateRef.current === 'off') return
      if (tSpeechEnd.current) {
        setLatency(Math.round(performance.now() - tSpeechEnd.current))
        tSpeechEnd.current = 0
      }
      pauseMic()
      set('speaking')
    },
    onIdle: () => { if (streamDone.current) backToListening() },
    onError: (msg) => setError(msg),
  }), [set, pauseMic, backToListening])

  const speechLang = (domainId) => (DOMAINS[domainId]?.kind === 'tech' ? 'tech' : domainId)

  // ── Um turno completo: áudio → texto → resposta falada ──
  const handleUtterance = useCallback(async (audio) => {
    const turn = ++turnRef.current
    tSpeechEnd.current = performance.now()
    setError(null)
    set('transcribing')

    const { settings, sendMessage } = latest.current
    let text = ''
    try {
      const res = await transcribeAudio(encodeWav(audio), settings.language, 'speech.wav')
      text = (res.transcript ?? '').trim()
    } catch (err) {
      setError(`Falha na transcrição: ${err.message}`)
    }
    if (turn !== turnRef.current) return
    if (!text) return backToListening()

    setCaption({ user: text, tutor: '' })
    set('thinking')  // sendMessage cria a sessão se ainda não houver uma

    const queue = queueRef.current
    queue.language = settings.language
    queue.speed = settings.speechRate ?? 1.0
    const splitter = new SentenceSplitter()
    streamDone.current = false

    await sendMessage(text, null, {
      fast: true,
      onText: (acc) => {
        if (turn !== turnRef.current) return
        splitter.push(acc).forEach(s => { queue.enqueue(s); setCaption(c => ({ ...c, tutor: (c.tutor + ' ' + s).trim() })) })
      },
      onDone: ({ message, error }) => {
        streamDone.current = true
        if (turn !== turnRef.current) return
        if (error) setError(error)
        splitter.flush(message || '').forEach(s => { queue.enqueue(s); setCaption(c => ({ ...c, tutor: (c.tutor + ' ' + s).trim() })) })
        if (!queue.busy) backToListening()
      },
    })
  }, [set, backToListening])

  // ── Liga/desliga ──
  const start = useCallback(async () => {
    if (stateRef.current !== 'off') return
    setError(null)
    setLatency(null)
    setCaption({ user: '', tutor: '' })
    set('loading')
    queueRef.current = newQueue()
    try {
      const vadModule = await import('@ricky0123/vad-web')
      const MicVAD = vadModule.MicVAD ?? vadModule.default?.MicVAD  // interop CommonJS
      vadRef.current = await MicVAD.new({
        model: 'v5',
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        getStream: () => navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }),
        positiveSpeechThreshold: 0.6,
        negativeSpeechThreshold: 0.4,
        redemptionMs: 700,      // pausa necessária para considerar que você terminou
        preSpeechPadMs: 300,
        minSpeechMs: 250,
        // Só reage a fala "real" (não a um estalo curto)
        onSpeechRealStart: () => { interrupt(true); if (stateRef.current === 'listening') set('userSpeaking') },
        onSpeechEnd: (audio) => handleUtterance(audio),
        onVADMisfire: () => { if (stateRef.current === 'userSpeaking') backToListening() },
      })
      vadRef.current.start()
      micPaused.current = false
      set('listening')
      // Saudação curta: confirma na hora que o áudio do tutor está funcionando
      const { settings } = latest.current
      queueRef.current.language = settings.language
      queueRef.current.speed = settings.speechRate ?? 1.0
      queueRef.current.enqueue(GREETING[speechLang(settings.language)] ?? GREETING.en)
    } catch (err) {
      setError(err.name === 'NotAllowedError'
        ? 'Permissão do microfone negada. Libere o microfone para este site no navegador.'
        : `Não foi possível iniciar o modo voz: ${err.message}`)
      set('off')
    }
  }, [set, newQueue, interrupt, handleUtterance, backToListening])

  const stop = useCallback(async () => {
    turnRef.current++
    queueRef.current?.stop()
    if (!streamDone.current) latest.current.stopStreaming()
    streamDone.current = true
    await vadRef.current?.destroy()
    vadRef.current = null
    micPaused.current = false
    set('off')
  }, [set])

  useEffect(() => () => { vadRef.current?.destroy() }, [])

  // Só em desenvolvimento: injeta um áudio como se fosse fala do microfone (testes sem mic)
  if (import.meta.env.DEV) {
    window.__voiceTest = {
      state: () => stateRef.current,
      audioBusy: () => Boolean(queueRef.current?.busy),
      bargeIn: () => interrupt(true),
      tapInterrupt: () => interrupt(false),
      utter: async (float32) => {
        if (!queueRef.current) queueRef.current = newQueue()
        set('listening')
        interrupt(true)
        return handleUtterance(float32)
      },
    }
  }

  return {
    state, error, latency, caption, start, stop,
    interrupt: () => interrupt(false),
    active: state !== 'off',
  }
}

// ── Contexto: a tela de voz (ChatArea) e o botão (InputBar) compartilham o mesmo modo voz ──
const VoiceContext = createContext(null)

export function VoiceProvider({ children }) {
  const voice = useVoiceMode()
  const [showText, setShowText] = useState(false)
  // Ao ligar o modo voz, abre na tela do círculo
  useEffect(() => { if (voice.active) setShowText(false) }, [voice.active])
  return (
    <VoiceContext.Provider value={{ ...voice, showText, setShowText }}>
      {children}
    </VoiceContext.Provider>
  )
}

export const useVoice = () => useContext(VoiceContext)
