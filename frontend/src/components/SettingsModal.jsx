// src/components/SettingsModal.jsx
import { useEffect, useState } from 'react'
import { X, Trash2 } from 'lucide-react'
import { DOMAINS, MODES, PROVIDERS, useApp } from '../context/AppContext'
import { getMemory, deleteMemoryItem, getMastery, deleteMasteryItem } from '../lib/api'

function Label({ children }) {
  return (
    <label className="block text-xs font-medium text-neutral-500 uppercase tracking-wider mb-2">
      {children}
    </label>
  )
}

function Chip({ active, onClick, children, className = '' }) {
  return (
    <button
      onClick={onClick}
      className={`
        px-3 py-2 rounded-xl border text-sm font-medium transition-all
        ${active
          ? 'border-neutral-900 bg-neutral-900 text-white'
          : 'border-neutral-200 text-neutral-700 hover:border-neutral-400 hover:bg-neutral-50'}
        ${className}
      `}
    >
      {children}
    </button>
  )
}

export default function SettingsModal() {
  const { settingsOpen, setSettingsOpen, settings, setSettings, health } = useApp()
  const [memory, setMemory] = useState([])
  const [mastery, setMastery] = useState([])

  useEffect(() => {
    if (settingsOpen) {
      getMemory(settings.language).then(setMemory)
      getMastery(settings.language).then(setMastery)
    }
  }, [settingsOpen, settings.language])

  if (!settingsOpen) return null

  const domain = DOMAINS[settings.language] ?? DOMAINS.en
  const providers = health.providers ?? {}

  function update(key, value) {
    setSettings(s => ({ ...s, [key]: value }))
  }

  async function removeMemory(id) {
    await deleteMemoryItem(id)
    setMemory(m => m.filter(x => x.id !== id))
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in"
      onClick={() => setSettingsOpen(false)}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 p-6 animate-slide-up max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-base font-semibold text-neutral-900">Configurações</h2>
          <button
            onClick={() => setSettingsOpen(false)}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-5">
          {/* Domínio */}
          <div>
            <Label>O que estudar</Label>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(DOMAINS).map(([id, info]) => (
                <Chip key={id} active={settings.language === id} onClick={() => update('language', id)}
                      className="flex items-center gap-2">
                  <span>{info.flag}</span><span>{info.label}</span>
                </Chip>
              ))}
            </div>
          </div>

          {/* Nível */}
          <div>
            <Label>Nível</Label>
            <div className="flex gap-2">
              {domain.levels.map(lvl => (
                <Chip key={lvl} active={settings.level === lvl} onClick={() => update('level', lvl)}
                      className="flex-1 px-1">
                  {lvl}
                </Chip>
              ))}
            </div>
          </div>

          {/* Modo */}
          <div>
            <Label>Modo</Label>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(MODES).map(([id, label]) => (
                <Chip key={id} active={settings.mode === id} onClick={() => update('mode', id)}>
                  {label}
                </Chip>
              ))}
            </div>
          </div>

          {/* Velocidade da voz */}
          <div>
            <Label>Velocidade da voz do tutor — {settings.speechRate.toFixed(2)}×</Label>
            <input
              type="range" min="0.7" max="1.3" step="0.05"
              value={settings.speechRate}
              onChange={e => update('speechRate', Number(e.target.value))}
              className="w-full accent-neutral-900"
            />
            <p className="mt-1 text-xs text-neutral-400">Mais devagar ajuda no início do aprendizado de um idioma.</p>
          </div>

          {/* Provedor LLM */}
          <div>
            <Label>Inteligência (LLM)</Label>
            <select
              value={settings.provider}
              onChange={e => update('provider', e.target.value)}
              className="w-full border border-neutral-200 rounded-xl px-3 py-2.5 text-sm text-neutral-900 bg-white focus:outline-none focus:border-neutral-400"
            >
              {Object.entries(PROVIDERS).map(([id, label]) => {
                const p = providers[id]
                const off = id !== 'auto' && p && !p.available
                return (
                  <option key={id} value={id} disabled={off}>
                    {label}{p?.model && id !== 'ollama' ? ` — ${p.model}` : ''}{off ? ' (indisponível)' : ''}
                  </option>
                )
              })}
            </select>

            {(settings.provider === 'ollama' || settings.provider === 'auto') && health.models.length > 0 && (
              <select
                value={settings.model}
                onChange={e => update('model', e.target.value)}
                className="mt-2 w-full border border-neutral-200 rounded-xl px-3 py-2 text-xs text-neutral-700 bg-white focus:outline-none focus:border-neutral-400"
              >
                {health.models.map(m => <option key={m} value={m}>Ollama: {m}</option>)}
              </select>
            )}

            <p className="mt-1.5 text-xs text-neutral-400">
              {['gemini', 'groq', 'ollama'].map(id => (
                <span key={id} className="mr-3">
                  {providers[id]?.available ? '🟢' : '⚪'} {id}
                </span>
              ))}
              {!providers.gemini?.available && !providers.groq?.available &&
                <span className="block mt-1">Adicione GEMINI_API_KEY / GROQ_API_KEY no arquivo .env</span>}
            </p>
          </div>

          {/* Mapa de domínio */}
          <div>
            <Label>Mapa de domínio — {domain.label}</Label>
            {mastery.length === 0 ? (
              <p className="text-xs text-neutral-400">Resolva exercícios para o tutor estimar seu domínio por conceito.</p>
            ) : (
              <ul className="space-y-1.5 max-h-48 overflow-y-auto">
                {mastery.map(m => (
                  <li key={m.id} className="group flex items-center gap-2 text-xs">
                    <span className="w-36 truncate text-neutral-700" title={m.concept}>{m.concept}</span>
                    <div className="flex-1 h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${m.score < 50 ? 'bg-red-400' : m.score < 75 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                           style={{ width: `${Math.round(m.score)}%` }} />
                    </div>
                    <span className="w-8 text-right tabular-nums text-neutral-500">{Math.round(m.score)}</span>
                    <button onClick={async () => { await deleteMasteryItem(m.id); setMastery(x => x.filter(i => i.id !== m.id)) }}
                            className="opacity-0 group-hover:opacity-100 text-neutral-300 hover:text-red-400">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Memória */}
          <div>
            <Label>Memória — pontos a melhorar em {domain.label}</Label>
            {memory.length === 0 ? (
              <p className="text-xs text-neutral-400">Nada registrado ainda. O tutor anota seus erros recorrentes aqui.</p>
            ) : (
              <ul className="space-y-1 max-h-48 overflow-y-auto">
                {memory.map(m => (
                  <li key={m.id} className="group flex items-start gap-2 text-xs text-neutral-700 bg-neutral-50 rounded-lg px-2.5 py-1.5">
                    <span className="shrink-0 text-neutral-400 tabular-nums">{m.count}×</span>
                    <span className="flex-1">{m.text}</span>
                    <button onClick={() => removeMemory(m.id)} title="Já dominei"
                            className="opacity-0 group-hover:opacity-100 text-neutral-300 hover:text-red-400">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={() => setSettingsOpen(false)}
            className="px-5 py-2.5 bg-neutral-900 text-white text-sm font-medium rounded-xl hover:bg-neutral-700 transition-colors"
          >
            Salvar
          </button>
        </div>
      </div>
    </div>
  )
}
