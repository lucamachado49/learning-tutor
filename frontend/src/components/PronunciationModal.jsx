// src/components/PronunciationModal.jsx
// Treino de pronúncia: ouça o modelo, grave a sua leitura e veja a nota por palavra e por som.
import { useEffect, useMemo, useState } from 'react'
import { X, Mic, Square, Volume2, Loader2, RotateCcw, ChevronLeft } from 'lucide-react'
import { DOMAINS, useApp } from '../context/AppContext'
import { useAudioRecorder } from '../hooks/useAudioRecorder'
import * as api from '../lib/api'

function scoreColor(score) {
  if (score >= 85) return 'text-emerald-600 bg-emerald-50 border-emerald-200'
  if (score >= 60) return 'text-amber-700 bg-amber-50 border-amber-200'
  return 'text-red-600 bg-red-50 border-red-200'
}

async function speak(text, language, rate) {
  const url = await api.fetchTTS(text, language, rate)
  const audio = new Audio(url)
  audio.onended = () => URL.revokeObjectURL(url)
  await audio.play()
}

// Frases curtas da mensagem do tutor, para escolher qual ler
function sentencesOf(text) {
  return (text ?? '')
    .replace(/[*_#`>]/g, '')
    .split(/(?<=[.!?…])\s+/)
    .map(s => s.trim())
    .filter(s => s.length >= 3 && s.length <= 200)
}

export default function PronunciationModal() {
  const { pronunciation, setPronunciation, settings } = useApp()
  const rec = useAudioRecorder()
  const [reference, setReference] = useState('')
  const [drills, setDrills]       = useState([])
  const [drill, setDrill]         = useState(null)
  const [result, setResult]       = useState(null)
  const [busy, setBusy]           = useState(false)
  const [error, setError]         = useState(null)
  const [openWord, setOpenWord]   = useState(null)

  const open = Boolean(pronunciation)
  const lang = settings.language
  const isLanguage = DOMAINS[lang]?.kind === 'language'
  const options = useMemo(() => sentencesOf(pronunciation?.text), [pronunciation])

  useEffect(() => {
    if (!open) return
    setResult(null); setError(null); setOpenWord(null); setDrill(null)
    setReference(options.length === 1 ? options[0] : '')
    if (isLanguage) api.getDrills(lang).then(list => {
      setDrills(list)
      // Vindo do painel "Hoje": abre direto no exercício do som pedido
      if (pronunciation?.sound) setDrill(list.find(d => d.sound === pronunciation.sound) ?? null)
    })
  }, [open, options, lang, isLanguage])

  // Avalia assim que a gravação termina
  useEffect(() => {
    if (!rec.audioBlob || !reference) return
    ;(async () => {
      setBusy(true); setError(null)
      try {
        setResult(await api.assessPronunciation(rec.audioBlob, reference, lang))
      } catch (err) {
        setError(err.message)
      } finally {
        setBusy(false)
        rec.reset()
      }
    })()
  }, [rec.audioBlob])

  if (!open) return null
  const close = () => { if (rec.isRecording) rec.stopRecording(); setPronunciation(null) }

  function choose(text) {
    setReference(text); setResult(null); setError(null); setOpenWord(null)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in" onClick={close}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl mx-4 p-6 animate-slide-up max-h-[90vh] overflow-y-auto"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-neutral-900 flex items-center gap-2">
            {reference && (options.length > 1 || drill || !pronunciation.text) && (
              <button onClick={() => choose('')} className="p-1 -ml-1 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
                <ChevronLeft className="w-4 h-4" />
              </button>
            )}
            Pronúncia — {DOMAINS[lang]?.flag} {DOMAINS[lang]?.label}
          </h2>
          <button onClick={close} className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        {!isLanguage && (
          <p className="text-sm text-neutral-500">Escolha Inglês ou Espanhol em Configurações para treinar pronúncia.</p>
        )}

        {/* 1. Escolher o que ler */}
        {isLanguage && !reference && (
          <div className="space-y-4">
            {options.length > 0 && (
              <div>
                <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider mb-2">Leia uma frase do tutor</p>
                <div className="space-y-1.5">
                  {options.map(s => (
                    <button key={s} onClick={() => choose(s)}
                            className="block w-full text-left text-sm px-3 py-2 rounded-xl border border-neutral-200 hover:border-neutral-400 hover:bg-neutral-50">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider mb-2">Ou treine um som difícil</p>
              {!drill ? (
                <div className="grid grid-cols-2 gap-1.5">
                  {drills.map(d => (
                    <button key={d.sound} onClick={() => setDrill(d)}
                            className="text-left text-sm px-3 py-2 rounded-xl border border-neutral-200 hover:border-neutral-400 hover:bg-neutral-50">
                      {d.title}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  <button onClick={() => setDrill(null)} className="text-xs text-neutral-500 hover:text-neutral-800">← todos os sons</button>
                  <p className="text-sm font-medium text-neutral-800">{drill.title}</p>
                  {drill.pairs.length > 0 && (
                    <div>
                      <p className="text-xs text-neutral-500 mb-1.5">Pares mínimos — ouça a diferença:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {drill.pairs.map(([a, b]) => (
                          <span key={a + b} className="flex items-center gap-1 text-xs border border-neutral-200 rounded-lg px-2 py-1">
                            <button onClick={() => speak(a, lang, 0.85)} className="hover:underline">{a}</button>
                            <span className="text-neutral-300">×</span>
                            <button onClick={() => speak(b, lang, 0.85)} className="hover:underline">{b}</button>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="space-y-1.5">
                    {drill.items.map(s => (
                      <button key={s} onClick={() => choose(s)}
                              className="block w-full text-left text-sm px-3 py-2 rounded-xl border border-neutral-200 hover:border-neutral-400 hover:bg-neutral-50">
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 2. Ler e gravar */}
        {isLanguage && reference && (
          <div>
            <p className="text-lg text-neutral-900 leading-relaxed mb-4">
              {result
                ? result.words.map((w, i) => (
                    <button key={i} onClick={() => setOpenWord(openWord === i ? null : i)}
                            className={`inline-block mr-1.5 mb-1.5 px-1.5 rounded-md border ${scoreColor(w.score)}`}>
                      {w.word}
                    </button>
                  ))
                : reference}
            </p>

            <div className="flex items-center gap-2">
              <button onClick={() => speak(reference, lang, settings.speechRate ?? 1)}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm border border-neutral-200 hover:bg-neutral-50">
                <Volume2 className="w-4 h-4" /> Ouvir modelo
              </button>
              {!rec.isRecording ? (
                <button onClick={() => { setResult(null); setOpenWord(null); rec.startRecording() }} disabled={busy}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm bg-neutral-900 text-white hover:bg-neutral-700 disabled:opacity-40">
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : result ? <RotateCcw className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                  {busy ? 'Avaliando…' : result ? 'Gravar de novo' : 'Gravar leitura'}
                </button>
              ) : (
                <button onClick={rec.stopRecording}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm bg-red-500 text-white animate-pulse">
                  <Square className="w-4 h-4" /> Parar ({rec.durationSec}s)
                </button>
              )}
              {result && (
                <span className={`ml-auto text-2xl font-semibold px-3 py-1 rounded-xl border ${scoreColor(result.score)}`}>
                  {result.score}
                </span>
              )}
            </div>

            {(error || rec.error) && <p className="mt-3 text-xs text-red-500">{error || rec.error}</p>}

            {/* Detalhe da palavra: som esperado × som produzido */}
            {result && openWord != null && (() => {
              const w = result.words[openWord]
              return (
                <div className="mt-4 p-3 rounded-xl bg-neutral-50 border border-neutral-200">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium">{w.word} — {w.score}</p>
                    <button onClick={() => speak(w.word, lang, 0.8)} className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800">
                      <Volume2 className="w-3.5 h-3.5" /> ouvir devagar
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {w.phones.map((p, k) => (
                      <span key={k} className={`text-sm font-mono px-2 py-1 rounded-lg border ${p.ok ? 'border-emerald-200 bg-white' : 'border-red-200 bg-red-50'}`}
                            title={p.ok ? 'certo' : p.got ? `você disse /${p.got}/` : 'som omitido'}>
                        /{p.expected}/
                        {!p.ok && <span className="ml-1 text-red-500">→ {p.got ? `/${p.got}/` : '∅'}</span>}
                      </span>
                    ))}
                    {w.extra.map((x, k) => (
                      <span key={'x' + k} className="text-sm font-mono px-2 py-1 rounded-lg border border-amber-200 bg-amber-50" title="som a mais">
                        +/{x}/
                      </span>
                    ))}
                  </div>
                </div>
              )
            })()}

            {result?.tips?.length > 0 && (
              <div className="mt-4 space-y-1.5">
                <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Dicas</p>
                {result.tips.map(t => <p key={t} className="text-sm text-neutral-700">• {t}</p>)}
              </div>
            )}
            {result && <p className="mt-3 text-[11px] text-neutral-400">Clique numa palavra para ver som por som.</p>}
          </div>
        )}
      </div>
    </div>
  )
}
