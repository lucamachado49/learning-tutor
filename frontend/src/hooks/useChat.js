// src/hooks/useChat.js
// Hook que gerencia o envio de mensagens e o consumo do SSE.

import { useCallback, useRef } from 'react'
import { useApp } from '../context/AppContext'
import * as api from '../lib/api'

export function useChat() {
  const {
    currentSession,
    settings,
    addMessage,
    updateLastMessage,
    setIsStreaming,
    createSession,
    updateSessionTitle,
  } = useApp()

  const abortRef = useRef(null)

  // Interrompe a resposta em andamento (barge-in do modo voz)
  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    updateLastMessage(msg => msg.streaming
      ? { ...msg, content: msg.content + ' …(interrompido)', streaming: false }
      : msg)
    setIsStreaming(false)
  }, [updateLastMessage, setIsStreaming])

  // hooks = { onText(textoAcumulado), onDone(resultado) } — usado pelo modo voz
  const sendMessage = useCallback(async (text, action = null, hooks = {}) => {
    if (!text.trim()) return

    // Se não houver sessão ativa, cria uma nova
    let session = currentSession
    if (!session) {
      session = await createSession()
      if (!session) return
    }

    // Adiciona mensagem do usuário ao estado local (otimista)
    addMessage({
      id:         `user-${Date.now()}`,
      role:       'user',
      content:    text.trim(),
      feedback:   '',
      created_at: new Date().toISOString(),
    })

    // Adiciona placeholder de streaming do assistente
    const placeholderId = `stream-${Date.now()}`
    addMessage({
      id:           placeholderId,
      role:         'assistant',
      content:      '',
      feedback:     '',
      streaming:    true,
      created_at:   new Date().toISOString(),
    })

    setIsStreaming(true)

    // Atualiza título da sessão com a primeira mensagem do usuário (UI)
    if (text.trim().length > 0) {
      const title = text.trim().slice(0, 55) + (text.trim().length > 55 ? '…' : '')
      updateSessionTitle(session.id, title)
    }

    const controller = new AbortController()
    abortRef.current = controller
    let acc = ''

    await api.streamChat({
      signal:    controller.signal,
      sessionId: session.id,
      message:   text.trim(),
      domain:      settings.language,
      level:       settings.level,
      mode:        settings.mode,
      provider:    settings.provider,
      ollamaModel: settings.model,
      action,
      fast:        Boolean(hooks.fast),

      onToken: (token) => {
        acc += token
        hooks.onText?.(acc)
        // Acumula tokens no placeholder
        updateLastMessage(msg => ({
          ...msg,
          content: msg.content + token,
        }))
      },

      onDone: ({ message, feedback, message_id, provider, citations, verified }) => {
        // Substitui placeholder pela mensagem final parseada
        updateLastMessage(msg => ({
          ...msg,
          id:       message_id || msg.id,
          content:  message,
          feedback: feedback,
          provider: provider,
          citations: citations,
          verified: verified,
          streaming: false,
        }))
        setIsStreaming(false)
        abortRef.current = null
        hooks.onDone?.({ message, feedback })
      },

      onError: (error) => {
        updateLastMessage(msg => ({
          ...msg,
          content:  `⚠️ ${error}`,
          streaming: false,
          isError:  true,
        }))
        setIsStreaming(false)
        abortRef.current = null
        hooks.onDone?.({ message: '', feedback: '', error })
      },
    })
  }, [currentSession, settings, addMessage, updateLastMessage, setIsStreaming, createSession, updateSessionTitle])

  return { sendMessage, stopStreaming }
}
