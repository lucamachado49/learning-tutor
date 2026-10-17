// src/hooks/useVoiceMode.js
// Modo conversa por voz: o VAD (Silero, no navegador) detecta quando você fala e quando para;
// a fala vai para o Whisper, a resposta do tutor é sintetizada FRASE A FRASE enquanto ainda é
// gerada, e falar por cima do tutor o interrompe (barge-in).

import { useCallback, useEffect, useRef, useState } from 'react'
// O VAD (e o runtime ONNX) só é carregado ao ligar o modo voz
import { useApp } from '../context/AppContext'
import { useChat } from './useChat'
import { transcribeAudio } from '../lib/api'
import { encodeWav, SentenceSplitter, SpeechQueue } from '../lib/speech'

// off → loading → listening ⇄ userSpeaking → transcribing → thinking → speaking → listening
export function useVoiceMode() {
  const { settings } = useApp()
  const { sendMessage, stopStreaming } = useChat()

  const [state, setState]   = useState('off')
  const [error, setError]   = useState(null)
  const [latency, setLatency] = useState(null)   // ms do fim da fala até o 1º áudio

  const vadRef     = useRef(null)
  const queueRef   = useRef(null)
  const stateRef   = useRef('off')
  const turnRef    = useRef(0)       // invalida turnos antigos após interrupção
  const streamDone = useRef(true)
  const tSpeechEnd = useRef(0)

  // Callbacks do VAD vivem muito tempo: leem sempre a versão mais recente via ref
  const latest = useRef({})
  latest.current = { sendMessage, stopStreaming, settings }

  const set = useCallback((s) => { stateRef.current = s; setState(s) }, [])

  const backToListening = useCallback(() => {
    if (stateRef.current !== 'off') set('listening')
  }, [set])

  // ── Interrupção: aluno começou a falar enquanto o tutor pensa/fala ──
  const bargeIn = useCallback(() => {
    const s = stateRef.current
    if (s === 'speaking' || s === 'thinking' || s === 'transcribing') {
      turnRef.current++
      queueRef.current?.stop()
      if (!streamDone.current) latest.current.stopStreaming()
      streamDone.current = true
      set('userSpeaking')  // agora é a vez do aluno
    }
  }, [set])

  // ── Um turno completo: áudio → texto → resposta falada ──
  const handleUtterance = useCallback(async (audio) => {
    const turn = ++turnRef.current
    tSpeechEnd.current = performance.now()
    set('transcribing')

    const { settings, sendMessage } = latest.current
    let text = ''
    try {
      const res = await transcribeAudio(encodeWav(audio), settings.language, 'speech.wav')
      text = (res.transcript ?? '').trim()
    } catch (err) {
      setError(err.message)
    }
    if (turn !== turnRef.current) return
    if (!text) return backToListening()

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
        splitter.push(acc).forEach(s => queue.enqueue(s))
      },
      onDone: ({ message }) => {
        streamDone.current = true
        if (turn !== turnRef.current) return
        splitter.flush(message || '').forEach(s => queue.enqueue(s))
        if (!queue.busy) backToListening()
      },
    })
  }, [set, backToListening])

  // ── Liga/desliga ──
  const start = useCallback(async () => {
    if (stateRef.current !== 'off') return
    setError(null)
    set('loading')
    queueRef.current = new SpeechQueue({
      onStart: () => {
        if (stateRef.current !== 'off') {
          if (tSpeechEnd.current) {
            setLatency(Math.round(performance.now() - tSpeechEnd.current))
            tSpeechEnd.current = 0
          }
          set('speaking')
        }
      },
      onIdle: () => { if (streamDone.current) backToListening() },
    })
    try {
      const vadModule = await import('@ricky0123/vad-web')
      const MicVAD = vadModule.MicVAD ?? vadModule.default?.MicVAD  // interop CommonJS
      vadRef.current = await MicVAD.new({
        model: 'v5',
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        // Cancelamento de eco: o microfone não deve "ouvir" a voz do próprio tutor
        getStream: () => navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }),
        positiveSpeechThreshold: 0.6,
        negativeSpeechThreshold: 0.4,
        redemptionMs: 700,      // pausa necessária para considerar que você terminou
        preSpeechPadMs: 300,
        minSpeechMs: 250,
        // Só interrompe com fala "real" (não com um estalo ou eco curto)
        onSpeechRealStart: () => { bargeIn(); set('userSpeaking') },
        onSpeechEnd: (audio) => handleUtterance(audio),
        onVADMisfire: () => { if (stateRef.current === 'userSpeaking') backToListening() },
      })
      vadRef.current.start()
      set('listening')
    } catch (err) {
      setError(err.name === 'NotAllowedError'
        ? 'Permissão do microfone negada. Libere o microfone para este site no navegador.'
        : `Não foi possível iniciar o modo voz: ${err.message}`)
      set('off')
    }
  }, [set, bargeIn, handleUtterance, backToListening])

  const stop = useCallback(async () => {
    turnRef.current++
    queueRef.current?.stop()
    if (!streamDone.current) latest.current.stopStreaming()
    streamDone.current = true
    await vadRef.current?.destroy()
    vadRef.current = null
    set('off')
  }, [set])

  useEffect(() => () => { vadRef.current?.destroy() }, [])

  // Só em desenvolvimento: injeta um áudio como se fosse fala do microfone (testes sem mic)
  if (import.meta.env.DEV) {
    window.__voiceTest = {
      state: () => stateRef.current,
      latency: () => latency,
      bargeIn,
      audioBusy: () => Boolean(queueRef.current?.busy),
      utter: async (float32) => {
        if (!queueRef.current) {
          queueRef.current = new SpeechQueue({
            onStart: () => {
              setLatency(Math.round(performance.now() - tSpeechEnd.current))
              set('speaking')
            },
            onIdle: () => { if (streamDone.current) backToListening() },
          })
        }
        set('listening')
        bargeIn()
        return handleUtterance(float32)
      },
    }
  }

  return { state, error, latency, start, stop, active: state !== 'off' }
}
