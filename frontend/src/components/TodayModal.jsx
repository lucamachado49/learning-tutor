// src/components/TodayModal.jsx
// "Hoje": revisão espaçada do dia, sequência de estudo e progresso nos últimos 30 dias.
import { useEffect, useState } from 'react'
import { X, Flame, CalendarCheck, Layers, PlayCircle, AudioLines, Table2, BarChart3 } from 'lucide-react'
import { DOMAINS, useApp } from '../context/AppContext'
import { useChat } from '../hooks/useChat'
import * as api from '../lib/api'

const KIND_LABEL = { mistake: 'Erro recorrente', concept: 'Conceito', sound: 'Som' }

function Stat({ icon: Icon, value, label }) {
  return (
    <div className="flex-1 rounded-xl border border-neutral-200 px-3 py-2.5">
      <p className="text-2xl font-semibold text-neutral-900 tabular-nums">{value}</p>
      <p className="text-[11px] text-neutral-500 flex items-center gap-1"><Icon className="w-3 h-3" />{label}</p>
    </div>
  )
}

// ── Gráficos (SVG simples; uma série cada, sem eixo duplo) ──
const W = 460, H = 120, PAD_L = 28, PAD_B = 18, PAD_T = 8

function useHover() {
  const [hover, setHover] = useState(null)
  return [hover, setHover]
}

function fmtDay(iso) {
  const [, m, d] = iso.split('-')
  return `${d}/${m}`
}

function LineChart({ series }) {
  const [hover, setHover] = useHover()
  const pts = series.map((p, i) => ({ ...p, i })).filter(p => p.avg_mastery != null)
  if (pts.length === 0) return <Empty text="Sem dados ainda — resolva exercícios para medir seu domínio." />
  const x = i => PAD_L + (i / (series.length - 1)) * (W - PAD_L - 6)
  const y = v => PAD_T + (1 - v / 100) * (H - PAD_T - PAD_B)
  const path = pts.map((p, k) => `${k ? 'L' : 'M'}${x(p.i)},${y(p.avg_mastery)}`).join(' ')
  const h = hover != null ? series[hover] : null
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onMouseLeave={() => setHover(null)}>
        {[0, 50, 100].map(v => (
          <g key={v}>
            <line x1={PAD_L} x2={W - 6} y1={y(v)} y2={y(v)} className="stroke-neutral-200" strokeWidth="1" />
            <text x={PAD_L - 6} y={y(v) + 3} textAnchor="end" className="fill-neutral-400 text-[9px]">{v}</text>
          </g>
        ))}
        <path d={path} fill="none" className="stroke-violet-500" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {pts.length === 1 && <circle cx={x(pts[0].i)} cy={y(pts[0].avg_mastery)} r="4" className="fill-violet-500" />}
        {h && h.avg_mastery != null && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={PAD_T} y2={H - PAD_B} className="stroke-neutral-300" strokeWidth="1" />
            <circle cx={x(hover)} cy={y(h.avg_mastery)} r="4" className="fill-violet-500 stroke-white" strokeWidth="2" />
          </>
        )}
        <text x={PAD_L} y={H - 4} className="fill-neutral-400 text-[9px]">{fmtDay(series[0].date)}</text>
        <text x={W - 6} y={H - 4} textAnchor="end" className="fill-neutral-400 text-[9px]">hoje</text>
        {/* áreas de hover maiores que a marca */}
        {series.map((_, i) => (
          <rect key={i} x={x(i) - (W / series.length) / 2} y={0} width={W / series.length} height={H}
                fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {h && <Tooltip pct={(x(hover) / W) * 100} lines={[fmtDay(h.date),
        h.avg_mastery != null ? `domínio médio ${h.avg_mastery} · ${h.concepts} conceitos` : 'sem dados']} />}
    </div>
  )
}

function BarChart({ series }) {
  const [hover, setHover] = useHover()
  const max = Math.max(4, ...series.map(p => p.reviews))
  if (!series.some(p => p.reviews)) return <Empty text="Nenhuma revisão nos últimos 30 dias." />
  const slot = (W - PAD_L - 6) / series.length
  const bw = Math.max(2, slot - 2)                       // 2px de respiro entre barras
  const y = v => PAD_T + (1 - v / max) * (H - PAD_T - PAD_B)
  const h = hover != null ? series[hover] : null
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onMouseLeave={() => setHover(null)}>
        {[0, max].map(v => (
          <g key={v}>
            <line x1={PAD_L} x2={W - 6} y1={y(v)} y2={y(v)} className="stroke-neutral-200" strokeWidth="1" />
            <text x={PAD_L - 6} y={y(v) + 3} textAnchor="end" className="fill-neutral-400 text-[9px]">{v}</text>
          </g>
        ))}
        {series.map((p, i) => p.reviews > 0 && (
          <rect key={i} x={PAD_L + i * slot + 1} y={y(p.reviews)} width={bw} height={y(0) - y(p.reviews)}
                rx={Math.min(4, bw / 2)} className={hover === i ? 'fill-violet-600' : 'fill-violet-500'} />
        ))}
        <text x={PAD_L} y={H - 4} className="fill-neutral-400 text-[9px]">{fmtDay(series[0].date)}</text>
        <text x={W - 6} y={H - 4} textAnchor="end" className="fill-neutral-400 text-[9px]">hoje</text>
        {series.map((_, i) => (
          <rect key={'h' + i} x={PAD_L + i * slot} y={0} width={slot} height={H} fill="transparent"
                onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {h && <Tooltip pct={((PAD_L + hover * slot + slot / 2) / W) * 100}
                     lines={[fmtDay(h.date), `${h.reviews} revisões · ${h.correct} acertos`]} />}
    </div>
  )
}

function Tooltip({ pct, lines }) {
  // Perto das bordas, ancora pelo lado de dentro para não ser cortada
  const shift = pct > 75 ? '-translate-x-full' : pct < 25 ? '' : '-translate-x-1/2'
  return (
    <div className={`pointer-events-none absolute -top-2 -translate-y-full ${shift} px-2 py-1 rounded-lg bg-neutral-900 text-white text-[11px] whitespace-nowrap shadow`}
         style={{ left: `${pct}%` }}>
      {lines.map(l => <div key={l}>{l}</div>)}
    </div>
  )
}

function Empty({ text }) {
  return <p className="text-xs text-neutral-400 py-6 text-center">{text}</p>
}

function DataTable({ series }) {
  return (
    <div className="max-h-48 overflow-y-auto text-xs">
      <table className="w-full">
        <thead className="text-neutral-500 sticky top-0 bg-white">
          <tr><th className="text-left py-1">Dia</th><th className="text-right">Domínio médio</th><th className="text-right">Revisões</th><th className="text-right">Acertos</th></tr>
        </thead>
        <tbody className="text-neutral-700 tabular-nums">
          {[...series].reverse().map(p => (
            <tr key={p.date} className="border-t border-neutral-100">
              <td className="py-1">{fmtDay(p.date)}</td>
              <td className="text-right">{p.avg_mastery ?? '—'}</td>
              <td className="text-right">{p.reviews}</td>
              <td className="text-right">{p.correct}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function TodayModal() {
  const { todayOpen, setTodayOpen, settings, setPronunciation, refreshToday } = useApp()
  const { sendMessage } = useChat()
  const [today, setToday]       = useState(null)
  const [progress, setProgress] = useState(null)
  const [asTable, setAsTable]   = useState(false)

  const domain = DOMAINS[settings.language]

  useEffect(() => {
    if (!todayOpen) return
    api.getReviewToday(settings.language).then(setToday)
    api.getProgress(settings.language).then(setProgress)
  }, [todayOpen, settings.language])

  if (!todayOpen) return null
  const close = () => { setTodayOpen(false); refreshToday() }

  const textItems  = today?.due.filter(i => i.kind !== 'sound') ?? []
  const soundItems = today?.due.filter(i => i.kind === 'sound') ?? []

  function startReview() {
    close()
    sendMessage('Vamos revisar os pontos de hoje.', 'review')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in" onClick={close}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl mx-4 p-6 animate-slide-up max-h-[90vh] overflow-y-auto"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-neutral-900">Hoje — {domain?.flag} {domain?.label}</h2>
          <button onClick={close} className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        {!today ? <p className="text-sm text-neutral-400">Carregando…</p> : (
          <>
            <div className="flex gap-2 mb-5">
              <Stat icon={Layers} value={today.total_due} label="para revisar hoje" />
              <Stat icon={CalendarCheck} value={today.done_today} label="feitas hoje" />
              <Stat icon={Flame} value={today.streak} label={today.streak === 1 ? 'dia seguido' : 'dias seguidos'} />
            </div>

            {today.total_due === 0 ? (
              <p className="text-sm text-neutral-600 mb-5">
                Nada para revisar agora 🎉
                {today.next_due && <> Próxima revisão: {new Date(today.next_due).toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'short' })}.</>}
              </p>
            ) : (
              <div className="space-y-4 mb-5">
                {textItems.length > 0 && (
                  <div>
                    <button onClick={startReview}
                            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-neutral-900 text-white text-sm font-medium hover:bg-neutral-700">
                      <PlayCircle className="w-4 h-4" /> Revisar {Math.min(5, textItems.length)} {textItems.length === 1 ? 'item' : 'itens'} com o tutor
                    </button>
                    <ul className="mt-2 space-y-1">
                      {textItems.slice(0, 5).map(i => (
                        <li key={i.id} className="text-xs text-neutral-600 flex gap-2">
                          <span className="shrink-0 text-neutral-400 w-24">{KIND_LABEL[i.kind]}</span>
                          <span className="truncate">{i.label}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {soundItems.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider mb-1.5">Sons para treinar</p>
                    <div className="flex flex-wrap gap-1.5">
                      {soundItems.map(i => (
                        <button key={i.id} onClick={() => { close(); setPronunciation({ text: '', sound: i.sound }) }}
                                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm border border-neutral-200 hover:bg-neutral-50">
                          <AudioLines className="w-3.5 h-3.5" /> /{i.sound}/
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Progresso */}
        {progress && (
          <div className="border-t border-neutral-100 pt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Últimos 30 dias</p>
              <button onClick={() => setAsTable(t => !t)} className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800">
                {asTable ? <><BarChart3 className="w-3.5 h-3.5" /> gráficos</> : <><Table2 className="w-3.5 h-3.5" /> tabela</>}
              </button>
            </div>
            {asTable ? <DataTable series={progress.series} /> : (
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-neutral-800 mb-1">Domínio médio (0–100)</p>
                  <LineChart series={progress.series} />
                </div>
                <div>
                  <p className="text-sm text-neutral-800 mb-1">Revisões por dia</p>
                  <BarChart series={progress.series} />
                </div>
              </div>
            )}
            {progress.weakest.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-neutral-500 uppercase tracking-wider mb-1.5">Pontos mais fracos</p>
                {progress.weakest.map(w => (
                  <div key={w.concept} className="flex items-center gap-2 text-xs py-0.5">
                    <span className="w-40 truncate text-neutral-700" title={w.concept}>{w.concept}</span>
                    <div className="flex-1 h-1.5 bg-neutral-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-violet-500" style={{ width: `${w.score}%` }} />
                    </div>
                    <span className="w-7 text-right tabular-nums text-neutral-500">{w.score}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
