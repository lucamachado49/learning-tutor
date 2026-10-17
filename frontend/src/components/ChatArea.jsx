// src/components/ChatArea.jsx
import { useEffect, useRef } from 'react'
import { MessageSquare } from 'lucide-react'
import { LANGUAGES, MODES, useApp } from '../context/AppContext'
import MessageItem from './MessageItem'
import VoicePanel from './VoicePanel'
import { useVoice } from '../hooks/useVoiceMode'

function EmptyState({ language, level, mode }) {
  const lang = LANGUAGES[language]
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 text-center">
      <div className="w-14 h-14 rounded-2xl bg-neutral-100 flex items-center justify-center mb-4">
        <MessageSquare className="w-7 h-7 text-neutral-400" />
      </div>
      <h2 className="text-lg font-semibold text-neutral-900 mb-1">
        {lang?.flag} Pronto para estudar {lang?.label}?
      </h2>
      <p className="text-sm text-neutral-500 max-w-xs leading-relaxed">
        Nível <strong className="text-neutral-700">{level}</strong> · modo{' '}
        <strong className="text-neutral-700">{MODES[mode]}</strong>.
        Escreva uma mensagem abaixo ou grave um áudio para começar.
      </p>
    </div>
  )
}

export default function ChatArea() {
  const { messages, currentSession, settings } = useApp()
  const bottomRef = useRef(null)
  const voice = useVoice()

  // Auto-scroll suave a cada nova mensagem / token
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (voice.active && !voice.showText) {
    return <VoicePanel onShowText={() => voice.setShowText(true)} />
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {!currentSession || messages.length === 0 ? (
        <EmptyState language={settings.language} level={settings.level} mode={settings.mode} />
      ) : (
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
          {messages.map(msg => (
            <MessageItem key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} className="h-px" />
        </div>
      )}
    </div>
  )
}
