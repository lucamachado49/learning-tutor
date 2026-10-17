// src/lib/api.js
// Camada de abstração para chamadas à API do backend FastAPI.

const BASE = '/api'

// ── Health ────────────────────────────────────────────────
export async function checkHealth() {
  // Pode lançar TypeError (network error) ou retornar 503 do proxy.
  // Ambos os casos devem resultar em { ollama: false } — deixamos o
  // caller tratar com try/catch.
  const r = await fetch(`${BASE}/health`)
  if (!r.ok) {
    // Proxy offline retorna 503 com JSON { detail, ollama, models }
    const body = await r.json().catch(() => ({}))
    throw Object.assign(new Error(body.detail ?? 'Backend offline'), body)
  }
  return r.json()
}

// ── Sessions ──────────────────────────────────────────────
export async function getSessions() {
  try {
    const r = await fetch(`${BASE}/sessions`)
    if (!r.ok) return []
    return r.json()
  } catch {
    return [] // backend offline — retorna lista vazia sem quebrar a UI
  }
}

export async function createSession(domain, level, mode, bookIds = []) {
  const r = await fetch(`${BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain, level, mode, book_ids: bookIds }),
  })
  if (!r.ok) throw new Error('Erro ao criar sessão')
  return r.json()
}

export async function getMessages(sessionId) {
  const r = await fetch(`${BASE}/sessions/${sessionId}/messages`)
  if (!r.ok) throw new Error('Erro ao carregar mensagens')
  return r.json()
}

export async function deleteSession(sessionId) {
  const r = await fetch(`${BASE}/sessions/${sessionId}`, { method: 'DELETE' })
  if (!r.ok) throw new Error('Erro ao deletar sessão')
  return r.json()
}

// ── Streaming chat (SSE via ReadableStream) ───────────────
/**
 * Envia mensagem ao backend e faz streaming token a token.
 * @param {object} params
 * @param {function} params.onToken   - callback(token: string) a cada token
 * @param {function} params.onDone    - callback({message, feedback, message_id})
 * @param {function} params.onError   - callback(error: string)
 */
export async function streamChat({ sessionId, message, domain, level, mode, provider, ollamaModel, action, onToken, onDone, onError }) {
  let response
  try {
    response = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        domain,
        level,
        mode,
        provider,
        ollama_model: ollamaModel,
        action,
      }),
    })
  } catch {
    onError('Não foi possível conectar ao backend. Execute: .\start_backend.ps1')
    return
  }

  if (!response.ok) {
    onError(`Erro do servidor: ${response.status} ${response.statusText}`)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue

        try {
          const data = JSON.parse(raw)
          if (data.error) {
            onError(data.error)
            return
          }
          if (!data.done && data.token) {
            onToken(data.token, data.provider)
          } else if (data.done) {
            onDone({
              message:    data.message    ?? '',
              feedback:   data.feedback   ?? '',
              message_id: data.message_id ?? '',
              provider:   data.provider   ?? '',
              citations:  data.citations  ?? [],
              verified:   data.verified   ?? false,
            })
            return
          }
        } catch {
          // linha SSE mal-formada — ignora
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

// ── STT ───────────────────────────────────────────────────
export async function transcribeAudio(audioBlob, language) {
  const form = new FormData()
  form.append('audio', audioBlob, 'recording.webm')
  form.append('language', language)
  const r = await fetch(`${BASE}/transcribe`, { method: 'POST', body: form })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Transcrição falhou')
  }
  return r.json() // { transcript: "..." }
}

// ── TTS ───────────────────────────────────────────────────
/**
 * Solicita síntese de voz e retorna uma ObjectURL para o áudio WAV.
 * Atenção: chame URL.revokeObjectURL(url) quando não for mais necessário.
 */
export async function fetchTTS(text, language) {
  const form = new FormData()
  form.append('text', text)
  form.append('language', language)
  const r = await fetch(`${BASE}/tts`, { method: 'POST', body: form })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail ?? 'TTS falhou')
  }
  const blob = await r.blob()
  return URL.createObjectURL(blob)
}

// ── Memória do aluno ──────────────────────────────────────
export async function getMemory(domain) {
  const r = await fetch(`${BASE}/memory/${domain}`)
  if (!r.ok) return []
  return r.json()
}

export async function deleteMemoryItem(id) {
  await fetch(`${BASE}/memory/item/${id}`, { method: 'DELETE' })
}

// ── Mapa de domínio ───────────────────────────────────────
export async function getMastery(domain) {
  const r = await fetch(`${BASE}/mastery/${domain}`)
  if (!r.ok) return []
  return r.json()
}

export async function deleteMasteryItem(id) {
  await fetch(`${BASE}/mastery/item/${id}`, { method: 'DELETE' })
}

// ── Biblioteca ────────────────────────────────────────────
export async function getBooks() {
  const r = await fetch(`${BASE}/books`)
  if (!r.ok) return []
  return r.json()
}

export async function uploadBook(file, domain) {
  const form = new FormData()
  form.append('file', file)
  form.append('domain', domain)
  const r = await fetch(`${BASE}/books`, { method: 'POST', body: form })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Falha no envio do PDF')
  }
  return r.json()
}

export async function deleteBook(id) {
  await fetch(`${BASE}/books/${id}`, { method: 'DELETE' })
}

export async function retryBook(id) {
  await fetch(`${BASE}/books/${id}/retry`, { method: 'POST' })
}

export async function setSessionBooks(sessionId, bookIds) {
  const r = await fetch(`${BASE}/sessions/${sessionId}/books`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ book_ids: bookIds }),
  })
  if (!r.ok) throw new Error('Erro ao vincular livros')
  return r.json()
}
