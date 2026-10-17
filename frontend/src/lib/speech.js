// src/lib/speech.js
// Peças do modo voz: WAV para o Whisper, divisão em frases e fila de reprodução (TTS por frase).

import { fetchTTS } from './api'
import { visiblePart } from '../components/Markdown'

// ── Float32 (16 kHz, saída do VAD) → WAV PCM 16-bit ───────
export function encodeWav(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const write = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)) }

  write(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); write(8, 'WAVE')
  write(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  write(36, 'data'); view.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

// ── Divide o texto em streaming em frases prontas para falar ──
// Recebe o texto ACUMULADO a cada token e devolve só as frases novas e completas.
export class SentenceSplitter {
  constructor(minChars = 25) {
    this.spoken = 0          // posição até onde já foi entregue
    this.minChars = minChars // evita clipes curtíssimos ("Ok.")
    this.inCode = false
  }

  push(fullText) {
    const text = visiblePart(fullText)  // só a [MENSAGEM], nunca o feedback
    const out = []
    // Fim de frase: . ! ? … : seguidos de espaço/quebra, ou quebra de parágrafo
    const re = /[.!?…:](?=\s)|\n\s*\n/g
    re.lastIndex = this.spoken
    let m
    while ((m = re.exec(text)) !== null) {
      const end = m.index + m[0].length
      const piece = text.slice(this.spoken, end).trim()
      if (piece.length >= this.minChars || /\n\s*\n/.test(m[0])) {
        if (piece) out.push(piece)
        this.spoken = end
      }
    }
    return out
  }

  flush(fullText) {
    const rest = visiblePart(fullText).slice(this.spoken).trim()
    this.spoken += rest.length
    return rest ? [rest] : []
  }
}

// ── Fila de fala: sintetiza em paralelo, toca em ordem ────
export class SpeechQueue {
  constructor({ onStart, onIdle } = {}) {
    this.items = []          // [{ promise: Promise<url> }]
    this.playing = false
    this.audio = null
    this.generation = 0      // invalida sínteses antigas após stop()
    this.onStart = onStart
    this.onIdle = onIdle
    this.language = 'en'
    this.speed = 1.0
  }

  enqueue(text) {
    const gen = this.generation
    // Começa a sintetizar já: enquanto uma frase toca, a próxima fica pronta
    const promise = fetchTTS(text, this.language, this.speed).catch(() => null)
    this.items.push({ promise, gen })
    if (!this.playing) this._next()
  }

  get busy() {
    return this.playing || this.items.length > 0
  }

  async _next() {
    const item = this.items.shift()
    if (!item) {
      this.playing = false
      this.onIdle?.()
      return
    }
    this.playing = true
    const url = await item.promise
    if (item.gen !== this.generation || !url) {
      if (url) URL.revokeObjectURL(url)
      return this._next()
    }
    this.onStart?.()
    this.audio = new Audio(url)
    const done = () => { URL.revokeObjectURL(url); this.audio = null; this._next() }
    this.audio.onended = done
    this.audio.onerror = done
    this.audio.play().catch(done)
  }

  // Barge-in: para tudo imediatamente
  stop() {
    this.generation++
    this.items = []
    if (this.audio) {
      this.audio.onended = null
      this.audio.pause()
      this.audio = null
    }
    this.playing = false
  }
}
