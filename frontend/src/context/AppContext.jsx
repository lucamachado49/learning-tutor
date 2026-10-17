// src/context/AppContext.jsx
// Estado global da aplicação via React Context.

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import * as api from '../lib/api'

// ── Constantes ────────────────────────────────────────────
// Espelha backend/domains.py. "language" em settings guarda o id do domínio.
export const CEFR_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
export const TECH_LEVELS = ['Iniciante', 'Intermediário', 'Avançado']

export const DOMAINS = {
  en:      { label: 'Inglês',             flag: '🇺🇸', kind: 'language', tts: true, levels: CEFR_LEVELS, defaultLevel: 'B1' },
  es:      { label: 'Espanhol',           flag: '🇪🇸', kind: 'language', tts: true, levels: CEFR_LEVELS, defaultLevel: 'A2' },
  math_ml: { label: 'Matemática p/ ML',   flag: '📐', kind: 'tech',     tts: true, levels: TECH_LEVELS, defaultLevel: 'Intermediário' },
  mle:     { label: 'ML Engineering',     flag: '🤖', kind: 'tech',     tts: true, levels: TECH_LEVELS, defaultLevel: 'Intermediário' },
  cto:     { label: 'CTO Skills',         flag: '🧭', kind: 'tech',     tts: true, levels: TECH_LEVELS, defaultLevel: 'Intermediário' },
}
// Alias mantido para componentes que ainda usam o nome antigo
export const LANGUAGES = DOMAINS

export const MODES = {
  conversation: 'Conversação livre',
  roleplay:     'Roleplay / simulação',
  lesson:       'Aula guiada',
  quiz:         'Exercícios / quiz',
}

export const PROVIDERS = {
  auto:   'Automático (melhor disponível)',
  gemini: 'Google Gemini',
  groq:   'Groq',
  ollama: 'Ollama (local)',
}

const EMPTY_HEALTH = { llm: false, providers: {}, ollama: false, models: [], whisper: false, tts: {} }

// ── Context ───────────────────────────────────────────────
const AppContext = createContext(null)

export function AppProvider({ children }) {
  // Sessões
  const [sessions, setSessions]             = useState([])
  const [currentSession, setCurrentSession] = useState(null)
  const [messages, setMessages]             = useState([])

  // UI
  const [sidebarOpen, setSidebarOpen]   = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [libraryOpen, setLibraryOpen]   = useState(false)
  const [isStreaming, setIsStreaming]   = useState(false)

  // Configurações
  const [settings, setSettingsRaw] = useState({
    language: 'en',            // id do domínio
    level:    'B1',
    mode:     'conversation',
    provider: 'auto',
    model:    'qwen2.5:7b',    // modelo do Ollama
    bookIds:  [],              // livros usados como base
  })

  // Ao trocar de domínio, ajusta o nível para um válido naquele domínio
  const setSettings = useCallback((updater) => {
    setSettingsRaw(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      const dom = DOMAINS[next.language] ?? DOMAINS.en
      if (!dom.levels.includes(next.level)) next.level = dom.defaultLevel
      return next
    })
  }, [])

  // Status do backend/Ollama
  const [health, setHealth]             = useState(EMPTY_HEALTH)
  const [backendOnline, setBackendOnline] = useState(false)

  const retryTimer     = useRef(null)
  const sessionsLoaded = useRef(false)
  // ref para evitar recrear doHealthCheck quando settings.model muda
  const settingsRef    = useRef(settings)
  useEffect(() => { settingsRef.current = settings }, [settings])

  // ── Health check com retry automático ────────────────────
  const doHealthCheck = useCallback(async () => {
    try {
      const data = await api.checkHealth()
      setHealth(data)
      setBackendOnline(true)

      // Ajusta modelo se o padrão não estiver instalado no Ollama
      if (data.models.length > 0 && !data.models.includes(settingsRef.current.model)) {
        // Prefere um modelo leve (7b) — a GPU tem pouca VRAM
        const light = data.models.find(m => /7b|:latest/.test(m)) ?? data.models[0]
        setSettings(s => ({ ...s, model: light }))
      }

      // Carrega sessões assim que o backend responder pela primeira vez
      if (!sessionsLoaded.current) {
        sessionsLoaded.current = true
        api.getSessions().then(setSessions).catch(console.error)
      }

      // Para o retry quando o backend voltar
      if (retryTimer.current) {
        clearInterval(retryTimer.current)
        retryTimer.current = null
      }
    } catch {
      // Backend offline — proxy retornou 503 ou ECONNREFUSED
      setBackendOnline(false)
      setHealth(EMPTY_HEALTH)

      // Tenta novamente a cada 5 s (sem criar múltiplos timers)
      if (!retryTimer.current) {
        retryTimer.current = setInterval(doHealthCheck, 5000)
      }
    }
  }, []) // sem deps — acessa settings via ref

  useEffect(() => {
    doHealthCheck()
    return () => {
      if (retryTimer.current) clearInterval(retryTimer.current)
    }
  }, [doHealthCheck])

  // ── Helpers de mensagens ──────────────────────────────────
  const addMessage = useCallback((msg) => {
    setMessages(prev => [...prev, msg])
  }, [])

  const updateLastMessage = useCallback((updaterFn) => {
    setMessages(prev => {
      if (prev.length === 0) return prev
      const updated = [...prev]
      updated[updated.length - 1] = updaterFn(updated[updated.length - 1])
      return updated
    })
  }, [])

  // ── Criar nova sessão ─────────────────────────────────────
  const createSession = useCallback(async () => {
    try {
      const { language, level, mode, bookIds } = settingsRef.current
      const session = await api.createSession(language, level, mode, bookIds)
      setSessions(prev => [session, ...prev])
      setCurrentSession(session)
      setMessages([])
      return session
    } catch (err) {
      console.error('createSession:', err)
      return null
    }
  }, [])

  // ── Selecionar sessão existente ───────────────────────────
  const selectSession = useCallback(async (session) => {
    if (isStreaming) return
    setCurrentSession(session)
    setMessages([])
    // Restaura domínio/nível/modo da sessão
    setSettings(s => ({
      ...s,
      language: session.domain ?? session.language ?? s.language,
      level:    session.level ?? s.level,
      mode:     session.mode ?? s.mode,
      bookIds:  session.book_ids ?? [],
    }))
    try {
      const msgs = await api.getMessages(session.id)
      setMessages(msgs)
    } catch (err) {
      console.error('selectSession:', err)
    }
  }, [isStreaming, setSettings])

  // ── Deletar sessão ────────────────────────────────────────
  const removeSession = useCallback(async (sessionId) => {
    try {
      await api.deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.id !== sessionId))
      if (currentSession?.id === sessionId) {
        setCurrentSession(null)
        setMessages([])
      }
    } catch (err) {
      console.error('removeSession:', err)
    }
  }, [currentSession])

  // ── Livros usados como base (sessão atual + próximas) ─────
  const setBookIds = useCallback(async (bookIds) => {
    setSettings(s => ({ ...s, bookIds }))
    if (currentSession) {
      try {
        const updated = await api.setSessionBooks(currentSession.id, bookIds)
        setCurrentSession(updated)
        setSessions(prev => prev.map(s => s.id === updated.id ? updated : s))
      } catch (err) {
        console.error('setBookIds:', err)
      }
    }
  }, [currentSession, setSettings])

  // ── Atualizar título da sessão no estado local ────────────
  const updateSessionTitle = useCallback((sessionId, title) => {
    setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, title } : s))
  }, [])

  return (
    <AppContext.Provider value={{
      // sessões
      sessions, setSessions,
      currentSession, setCurrentSession,
      messages, setMessages,
      addMessage, updateLastMessage,
      createSession, selectSession, removeSession, updateSessionTitle,
      // ui
      sidebarOpen, setSidebarOpen,
      settingsOpen, setSettingsOpen,
      libraryOpen, setLibraryOpen,
      isStreaming, setIsStreaming,
      // config
      settings, setSettings, setBookIds,
      // status
      health, backendOnline,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export const useApp = () => {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp deve ser usado dentro de AppProvider')
  return ctx
}
