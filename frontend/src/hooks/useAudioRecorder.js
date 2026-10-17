// src/hooks/useAudioRecorder.js
// Hook para gravação de áudio via MediaRecorder API nativa do navegador.

import { useCallback, useRef, useState } from 'react'

/**
 * Prefere WebM/Opus (suportado no Chrome/Edge) com fallback para audio/ogg.
 * O backend faster-whisper aceita ambos.
 */
function getSupportedMimeType() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']
  return types.find(t => MediaRecorder.isTypeSupported(t)) ?? ''
}

export function useAudioRecorder() {
  const [isRecording, setIsRecording]       = useState(false)
  const [audioBlob, setAudioBlob]           = useState(null)
  const [error, setError]                   = useState(null)
  const [durationSec, setDurationSec]       = useState(0)

  const mediaRecorderRef = useRef(null)
  const chunksRef        = useRef([])
  const streamRef        = useRef(null)
  const timerRef         = useRef(null)

  const startRecording = useCallback(async () => {
    setError(null)
    setAudioBlob(null)
    setDurationSec(0)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      streamRef.current = stream

      const mimeType = getSupportedMimeType()
      const options  = mimeType ? { mimeType } : {}
      const recorder = new MediaRecorder(stream, options)
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
        setAudioBlob(blob)
        // Libera microfone
        streamRef.current?.getTracks().forEach(t => t.stop())
        clearInterval(timerRef.current)
      }

      recorder.start(250) // coleta chunks a cada 250 ms
      setIsRecording(true)

      // Contador de duração
      timerRef.current = setInterval(() => setDurationSec(s => s + 1), 1000)
    } catch (err) {
      setError(err.message ?? 'Não foi possível acessar o microfone.')
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    setIsRecording(false)
    clearInterval(timerRef.current)
  }, [])

  const reset = useCallback(() => {
    setAudioBlob(null)
    setDurationSec(0)
    setError(null)
  }, [])

  return {
    isRecording,
    audioBlob,
    durationSec,
    error,
    startRecording,
    stopRecording,
    reset,
  }
}
