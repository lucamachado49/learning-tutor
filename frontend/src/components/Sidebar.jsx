// src/components/Sidebar.jsx
import { useState } from 'react'
import { MessageSquarePlus, Settings, Trash2, ChevronLeft, ChevronRight, Bot, Circle, Library } from 'lucide-react'
import { LANGUAGES, useApp } from '../context/AppContext'

function formatDate(iso) {
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now - d) / 86400000)
  if (diffDays === 0) return 'Hoje'
  if (diffDays === 1) return 'Ontem'
  if (diffDays < 7) return `${diffDays}d atrás`
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

export default function Sidebar() {
  const {
    sessions, currentSession, isStreaming,
    createSession, selectSession, removeSession,
    sidebarOpen, setSidebarOpen,
    setSettingsOpen, setLibraryOpen,
    settings, health, backendOnline,
  } = useApp()

  const [deletingId, setDeletingId] = useState(null)

  async function handleNew() {
    if (isStreaming) return
    await createSession()
  }

  async function handleDelete(e, id) {
    e.stopPropagation()
    setDeletingId(id)
    await removeSession(id)
    setDeletingId(null)
  }

  const langInfo = LANGUAGES[settings.language]

  return (
    <>
      {/* Sidebar */}
      <aside
        className={`
          flex flex-col h-full border-r border-neutral-200 bg-neutral-50
          transition-all duration-200 ease-in-out overflow-hidden shrink-0
          ${sidebarOpen ? 'w-64' : 'w-0'}
        `}
      >
        <div className="flex flex-col h-full w-64">
          {/* Logo / header */}
          <div className="flex items-center gap-2.5 px-4 py-4 border-b border-neutral-200">
            <div className="w-8 h-8 rounded-lg bg-neutral-900 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-neutral-900 truncate">Learning Tutor</p>
              <p className="text-xs text-neutral-400 truncate">
                {langInfo?.flag} {langInfo?.label} · {settings.level}
              </p>
            </div>
          </div>

          {/* Nova conversa */}
          <div className="px-3 pt-3">
            <button
              onClick={handleNew}
              disabled={isStreaming}
              className="
                w-full flex items-center gap-2 px-3 py-2.5 rounded-xl
                border border-dashed border-neutral-300
                text-sm text-neutral-600 font-medium
                hover:bg-white hover:border-neutral-400 hover:text-neutral-900
                disabled:opacity-40 disabled:cursor-not-allowed
                transition-all
              "
            >
              <MessageSquarePlus className="w-4 h-4 shrink-0" />
              Nova conversa
            </button>
          </div>

          {/* Lista de sessões */}
          <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
            {sessions.length === 0 ? (
              <p className="text-xs text-neutral-400 text-center py-8 px-3">
                Nenhuma conversa ainda.
              </p>
            ) : (
              sessions.map(session => {
                const isActive = currentSession?.id === session.id
                return (
                  <div
                    key={session.id}
                    onClick={() => selectSession(session)}
                    className={`
                      group relative flex items-start gap-2 px-3 py-2.5 rounded-xl cursor-pointer
                      transition-colors
                      ${isActive
                        ? 'bg-white border border-neutral-200 shadow-sm'
                        : 'hover:bg-white hover:border hover:border-neutral-100'}
                    `}
                  >
                    {/* Indicador de idioma */}
                    <span className="text-base leading-none mt-0.5 shrink-0">
                      {LANGUAGES[session.language]?.flag ?? '🌐'}
                    </span>

                    <div className="min-w-0 flex-1">
                      <p className={`text-xs font-medium truncate leading-snug ${isActive ? 'text-neutral-900' : 'text-neutral-700'}`}>
                        {session.title}
                      </p>
                      <p className="text-xs text-neutral-400 mt-0.5">
                        {session.level} · {formatDate(session.updated_at)}
                      </p>
                    </div>

                    {/* Botão deletar */}
                    <button
                      onClick={(e) => handleDelete(e, session.id)}
                      disabled={deletingId === session.id || isStreaming}
                      className="
                        shrink-0 p-1 rounded-lg opacity-0 group-hover:opacity-100
                        text-neutral-300 hover:text-red-400 hover:bg-red-50
                        disabled:opacity-20 transition-all
                      "
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )
              })
            )}
          </div>

          {/* Footer: status + configurações */}
          <div className="border-t border-neutral-200 px-3 py-3 space-y-1">
            {/* Status Ollama */}
            {/* Status: backend → Ollama */}
            <div className="flex items-center gap-2 px-2 py-1.5">
              <Circle className={`w-2 h-2 fill-current ${
                !backendOnline  ? 'text-red-400'
                : health.llm    ? 'text-emerald-400'
                :                  'text-amber-400'
              }`} />
              <span className="text-xs text-neutral-500">
                {!backendOnline
                  ? <>
                      <span className="text-red-500 font-medium">Backend offline</span>
                      <br />
                      <span className="text-neutral-400">.\start_backend.ps1</span>
                    </>
                  : health.llm
                    ? `LLM: ${['gemini', 'groq', 'ollama'].filter(p => health.providers?.[p]?.available).join(' · ')}`
                    : <>
                        <span className="text-amber-600 font-medium">Nenhum LLM disponível</span>
                        <br />
                        <span className="text-neutral-400">configure o .env ou rode ollama serve</span>
                      </>
                }
              </span>
            </div>

            <button
              onClick={() => setLibraryOpen(true)}
              className="
                w-full flex items-center gap-2 px-3 py-2.5 rounded-xl
                text-sm text-neutral-600 hover:bg-white hover:text-neutral-900
                transition-colors
              "
            >
              <Library className="w-4 h-4" />
              Biblioteca
            </button>

            <button
              onClick={() => setSettingsOpen(true)}
              className="
                w-full flex items-center gap-2 px-3 py-2.5 rounded-xl
                text-sm text-neutral-600 hover:bg-white hover:text-neutral-900
                transition-colors
              "
            >
              <Settings className="w-4 h-4" />
              Configurações
            </button>
          </div>
        </div>
      </aside>

      {/* Toggle button */}
      <button
        onClick={() => setSidebarOpen(o => !o)}
        className="
          absolute left-0 top-1/2 -translate-y-1/2 z-20
          w-5 h-10 flex items-center justify-center
          bg-white border border-neutral-200 rounded-r-lg
          text-neutral-400 hover:text-neutral-700
          shadow-sm transition-all hover:shadow
          translate-x-[var(--sidebar-w)]
        "
        style={{ '--sidebar-w': sidebarOpen ? '256px' : '0px' }}
      >
        {sidebarOpen
          ? <ChevronLeft className="w-3 h-3" />
          : <ChevronRight className="w-3 h-3" />
        }
      </button>
    </>
  )
}
