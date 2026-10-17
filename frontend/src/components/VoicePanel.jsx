// src/components/VoicePanel.jsx
// Tela do modo conversa: um círculo que mostra quem está falando, sem texto por padrão.
import { useState } from 'react'
import { PhoneOff, Captions, MessageSquareText } from 'lucide-react'
import { DOMAINS, useApp } from '../context/AppContext'
import { useVoice } from '../hooks/useVoiceMode'

const LOOK = {
  loading:      { label: 'Preparando…',                 ring: 'bg-neutral-300',  core: 'bg-neutral-400', anim: 'animate-pulse' },
  listening:    { label: 'Pode falar',                  ring: 'bg-emerald-200',  core: 'bg-emerald-500', anim: 'animate-[breathe_2.4s_ease-in-out_infinite]' },
  userSpeaking: { label: 'Ouvindo você…',               ring: 'bg-emerald-300',  core: 'bg-emerald-600', anim: 'animate-[breathe_0.7s_ease-in-out_infinite]' },
  transcribing: { label: 'Entendendo…',                 ring: 'bg-sky-200',      core: 'bg-sky-500',     anim: 'animate-pulse' },
  thinking:     { label: 'Pensando…',                   ring: 'bg-amber-200',    core: 'bg-amber-500',   anim: 'animate-pulse' },
  speaking:     { label: 'Falando — toque para interromper', ring: 'bg-violet-200', core: 'bg-violet-500', anim: 'animate-[breathe_0.9s_ease-in-out_infinite]' },
}

export default function VoicePanel({ onShowText }) {
  const voice = useVoice()
  const { settings } = useApp()
  const [captions, setCaptions] = useState(false)
  const look = LOOK[voice.state] ?? LOOK.loading
  const domain = DOMAINS[settings.language]
  const canInterrupt = voice.state === 'speaking' || voice.state === 'thinking'

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 select-none">
      <p className="text-sm text-neutral-400 mb-10">
        {domain?.flag} Conversa em {domain?.label} · {settings.level}
      </p>

      {/* Círculo */}
      <button
        onClick={() => canInterrupt && voice.interrupt()}
        className={`relative w-44 h-44 rounded-full flex items-center justify-center ${canInterrupt ? 'cursor-pointer' : 'cursor-default'}`}
        title={canInterrupt ? 'Interromper o tutor' : look.label}
      >
        <span className={`absolute inset-0 rounded-full opacity-60 ${look.ring} ${look.anim}`} />
        <span className={`relative w-28 h-28 rounded-full shadow-lg transition-colors duration-300 ${look.core}`} />
      </button>

      <p className="mt-8 text-base font-medium text-neutral-800">{look.label}</p>
      {voice.latency != null && (
        <p className="mt-1 text-xs text-neutral-400">última resposta em {(voice.latency / 1000).toFixed(1)} s</p>
      )}
      {voice.error && <p className="mt-3 text-xs text-red-500 max-w-sm text-center">{voice.error}</p>}

      {/* Legendas opcionais */}
      {captions && (voice.caption.user || voice.caption.tutor) && (
        <div className="mt-8 max-w-xl w-full space-y-2 text-sm">
          {voice.caption.user && <p className="text-neutral-500"><span className="font-medium">Você:</span> {voice.caption.user}</p>}
          {voice.caption.tutor && <p className="text-neutral-800"><span className="font-medium">Tutor:</span> {voice.caption.tutor}</p>}
        </div>
      )}

      <div className="mt-10 flex items-center gap-2">
        <button onClick={() => setCaptions(c => !c)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs border transition-colors
                  ${captions ? 'border-neutral-900 text-neutral-900' : 'border-neutral-200 text-neutral-500 hover:text-neutral-800'}`}>
          <Captions className="w-3.5 h-3.5" /> Legendas
        </button>
        <button onClick={onShowText}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs border border-neutral-200 text-neutral-500 hover:text-neutral-800">
          <MessageSquareText className="w-3.5 h-3.5" /> Ver conversa e correções
        </button>
        <button onClick={voice.stop}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs bg-red-50 text-red-600 hover:bg-red-100">
          <PhoneOff className="w-3.5 h-3.5" /> Encerrar
        </button>
      </div>

      {!settings.voiceBargeIn && (
        <p className="mt-6 text-[11px] text-neutral-400 max-w-sm text-center">
          O microfone pausa enquanto o tutor fala (evita eco). Usando fone de ouvido?
          Ative “Interromper falando” em Configurações.
        </p>
      )}
    </div>
  )
}
