import { trainVisual } from '@/lib/train-service'
import type { Leg } from '@/lib/contract'
import { ArrowLeft, ArrowRight, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Clock3, Info, Loader2, Pause, Play, Route, ShieldCheck, Sparkles, TrainFront, Umbrella, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useStore, type Tab } from '@/lib/store'
import { fmtDate, fmtTime } from '@/lib/geo'
import { toggleMotion, useReducedMotion } from '@/lib/motion'
import { StartPanel } from '@/features/share-parser/components/StartPanel'
import { InstallButton, OfflinePill } from './StatusPills'
import { travelerAdvice } from '@/features/recommendation/components/AdvicePanel'
import '@/single-screen.css'

const GlobeMap = lazy(() => import('@/features/globe-map/components/GlobeMap').then(m => ({ default: m.GlobeMap })))
const tabs: { id: Tab; label: string; icon: typeof Route }[] = [{ id: 'plan', label: 'My journey', icon: Route }, { id: 'advice', label: 'What next?', icon: Umbrella }, { id: 'evidence', label: 'Why?', icon: Info }]
function ServiceTrain({ leg }: { leg: Leg }) {
  const style = trainVisual(leg)
  return <svg width="52" height="67" viewBox="0 0 64 72" role="img" aria-label={`${style.label} illustration`}><rect width="64" height="72" rx="15" fill="#e4ebe5" /><path d="M7 57H57M7 61H57" stroke="#879b91" strokeWidth="2" /><path d={style.kind === 'ice' ? 'M9 29H36Q47 29 56 48H9Z' : 'M9 29H46Q54 29 54 48H9Z'} fill={style.color} stroke="#61766e" /><path d="M10 44H51" stroke={style.kind === 'unknown' ? '#61766e' : '#da3c33'} strokeWidth="3" /><path d="M13 33H39V39H13Z" fill="#263f47" />{Array.from({ length: style.doors }, (_, i) => <rect key={i} x={14 + i * 11} y="32" width="4" height="15" rx="1" fill="#c3cdca" />)}<circle cx="18" cy="51" r="4" fill="#344b43" /><circle cx="44" cy="51" r="4" fill="#344b43" /></svg>
}
function Art({ kind = 0 }: { kind?: number }) { return <span className="travel-art" style={{ backgroundPosition: `${kind * 50}% center` }} aria-hidden="true" /> }
function Pager({ index, count, onChange, label }: { index: number; count: number; onChange: (index: number) => void; label: string }) {
  return <div className="travel-pager"><button type="button" aria-label={`Previous ${label}`} disabled={index <= 0} onClick={() => onChange(index - 1)}><ChevronLeft size={18} /></button><span>{label} {index + 1} / {count}</span><button type="button" aria-label={`Next ${label}`} disabled={index >= count - 1} onClick={() => onChange(index + 1)}><ChevronRight size={18} /></button></div>
}
function TextPages({ text }: { text: string }) {
  const [page, setPage] = useState(0)
  // Preserve every word, with short pages instead of a growing scroll panel.
  const words = text.split(/\s+/); const pages: string[] = []; let current = ''
  for (const word of words) { if (current.length + word.length > 180) { pages.push(current); current = '' } current += `${current ? ' ' : ''}${word}` }
  if (current) pages.push(current)
  useEffect(() => setPage(0), [text])
  const index = Math.min(page, Math.max(0, pages.length - 1))
  return <><p className="travel-copy">{pages[index]}</p>{pages.length > 1 && <Pager label="page" index={index} count={pages.length} onChange={setPage} />}</>
}
// One of the model's summary sentences, shorter: the same facts, station names and delays in fewer words.
function compactSentence(sentence: string) {
  let m: RegExpMatchArray | null
  if ((m = sentence.match(/^The train left (.+?) (-?\d+) minutes late/))) return `The train left ${m[1]} ${m[2]} min late.`
  if ((m = sentence.match(/^Today the previous \d+ trains? .*?reached (.+?) ((?:-?\d+, )*-?\d+) minutes late/))) {
    const delays = m[2].split(', ').map(Number)
    if (delays.length === 1) return `The train before it reached ${m[1]} ${delays[0]} min late.`
    const list = delays.length <= 3 ? `${delays.slice(0, -1).join(', ')} and ${delays.at(-1)}` : `between ${Math.min(...delays)} and ${Math.max(...delays)}`
    return `The last ${delays.length} trains reached ${m[1]} ${list} min late.`
  }
  if ((m = sentence.match(/^No earlier train of this type towards .+? reached (.+?) in the last 6 hours/))) return `No earlier train of this type reached ${m[1]} in 6 hours.`
  if ((m = sentence.match(/^At (.+?), (\d+%) of stops ran at least 6 minutes late in the last 3 hours/))) return `${m[2]} of stops at ${m[1]} ran late in the last 3 hours.`
  return sentence.replace(/(;|, the latest|, against).*$/, '').replace(/\.?$/, '.')
}
const compactTake = (summary: string) => summary.split(/(?<=\.)\s+(?=[A-Z])/).slice(0, 2).map(compactSentence).join(' ')
function TrainTake({ index }: { index: number }) {
  // The model's two summary sentences on this train, shortened, woven into its card once written (about 15 s).
  const e = useStore().explanations[index]
  if (!e || e.status === 'error') return null
  if (e.status === 'loading') return <span className="mt-2 block space-y-1.5" aria-live="polite"><span className="sr-only">The model is reading this train.</span><span className="block h-1.5 w-11/12 animate-pulse rounded-full bg-[#e3e8da]" /><span className="block h-1.5 w-7/12 animate-pulse rounded-full bg-[#e3e8da] [animation-delay:200ms]" /></span>
  return <span className="mt-2 flex gap-1.5 text-[11px] leading-snug text-[#4d5c46] animate-in fade-in slide-in-from-bottom-1 duration-700" aria-live="polite"><Sparkles size={12} className="mt-px shrink-0 text-[#7c9070]" /><span>{compactTake(e.summary)}</span></span>
}
function ModelReasoning({ index }: { index: number }) {
  // The full rationale the model wrote: a dropdown at the bottom of the panel that opens downwards.
  const e = useStore().explanations[index]
  if (e?.status !== 'done') return null
  return <details className="group flex-1 border-t border-[#e6eadf] pt-2.5 animate-in fade-in duration-700">
    <summary className="flex cursor-pointer list-none items-center gap-1 [&::-webkit-details-marker]:hidden"><span className="travel-kicker">IN THE MODEL’S OWN WORDS</span><ChevronDown size={12} className="text-[#687f5d] transition-transform group-open:rotate-180" /></summary>
    <p className="travel-copy mt-1.5 text-[#55624d]">{e.text}</p><p className="travel-fine mt-1.5">Written freely by the model, so it can misstate numbers; the estimate above reads the exact inputs.</p>
  </details>
}
function JourneyPanel() {
  const s = useStore(); const journey = s.journey!; const index = Math.min(s.selectedLeg ?? 0, journey.legs.length - 1)
  const leg = journey.legs[index], forecast = s.prediction?.legs[index], next = journey.legs[index + 1]
  const offline = !!forecast?.expectedDelayMinutes.sources.some(source => source.includes('offline estimate'))
  const change = next ? (Date.parse(next.plannedDeparture) - Date.parse(leg.plannedArrival)) / 60000 : null
  const left = change != null && forecast ? Math.round(change - forecast.expectedDelayMinutes.value) : null
  const risk = s.prediction?.planFailProbability.value
  const direct = journey.legs.length === 1
  return <div className="travel-panel-body min-h-full">
    <div className="travel-verdict"><div><span className="travel-kicker">YOUR WHOLE JOURNEY</span><h2>{risk == null ? s.error ? 'Forecast unavailable.' : 'Checking your connections…' : journey.legs.length === 1 ? 'One train. A simpler journey.' : risk < .15 ? 'This connection looks good.' : 'Give your day a backup plan.'}</h2></div><strong>{risk == null ? '—' : direct ? `+${Math.round(forecast?.expectedDelayMinutes.value ?? 0)}` : `${Math.round(risk * 100)}%`}<small>{direct ? 'minutes estimated arrival delay' : 'estimated plan-failure risk'}</small></strong></div>
    <Pager label="train" index={index} count={journey.legs.length} onChange={i => s.dispatch({ type: 'selectLeg', index: i })} />
    <button type="button" className="travel-train-card" onClick={() => s.dispatch({ type: 'selectLeg', index })} aria-label={`Focus map on ${leg.trainId}`}>
      <ServiceTrain leg={leg} /><div><span className="travel-kicker">{trainVisual(leg).label} · {index + 1}</span><h3>{leg.trainId}<em>{forecast ? `+${Math.round(forecast.expectedDelayMinutes.value)} min` : 'Checking…'}</em></h3><p>{leg.from.name} <ArrowRight size={12} /> {leg.to.name}</p><small>{fmtTime(leg.plannedDeparture)} — {fmtTime(leg.plannedArrival)} · scheduled</small>{offline && <span className="mt-1 block text-[10px] text-[#9a7b4f]">Offline estimate · DB live data unavailable, based on timetable and history</span>}<TrainTake index={index} /></div>
    </button>
    {!!leg.disruptions?.length && <details className="travel-fine"><summary>Reported service notice</summary><TextPages text={leg.disruptions.map(n => `${n.text} Source: ${n.source}.`).join(' ')} /></details>}    <div className="travel-connection" data-tight={left != null && left < 8}><Clock3 size={18} /><div><strong>{!next ? 'Your final stop.' : left == null ? `${Math.round(change!)} minutes scheduled to change` : left < 0 ? `${Math.abs(left)} min past the next departure` : `${left} minutes left to change`}</strong><p>{next ? 'Assumes the next train leaves on time; walking time not included.' : 'An arrival delay can still affect your plans after the train.'}</p></div></div>
    <ModelReasoning index={index} />
  </div>
}
function AdviceCompact() {
  const s = useStore(); const [view, setView] = useState<'advice' | 'leave' | 'alternative' | 'recovery'>('advice'); const [legIndex, setLegIndex] = useState(0); const [loading, setLoading] = useState(false)
  const journey = s.journey!, rec = s.recommendation
  useEffect(() => { s.dispatch({ type: 'overlay', overlay: view === 'alternative' && rec?.alternative ? 'alternative' : 'none' }) }, [view, rec?.alternative, s.dispatch])
  const depart = journey.legs[0].plannedDeparture
  const leave = new Date(Date.parse(depart) - (s.doorToStationMin + 5) * 60000).toISOString()
  const alt = rec?.alternative; const leg = alt?.legs[Math.min(legIndex, alt.legs.length - 1)]
  const recovery = s.reroute?.options[s.rerouteChoice]
  return <div className="travel-panel-body">
    <div className="travel-subtabs" aria-label="Recommendations">{(['advice', 'leave', 'alternative', 'recovery'] as const).map((v, i) => <button type="button" key={v} aria-pressed={view === v} onClick={() => { setView(v); setLegIndex(0) }}>{['Best next step', 'Leave by', 'Other route', 'Disrupted?'][i]}</button>)}</div>
    {view === 'advice' && <><div className="travel-feature"><Art kind={1} /><div><span className="travel-kicker">COMFORT OVER A SPRINT</span><h2>{rec?.verdict === 'good' ? 'Keep this connection.' : rec ? 'A little breathing room.' : 'Advice is not available yet.'}</h2></div></div><TextPages text={rec ? travelerAdvice(rec) : 'Your route is saved. Retry the check, or confirm the next departures in DB Navigator.'} />{rec?.bufferMinutes != null && <p className="travel-fine"><b>+{rec.bufferMinutes} min</b> suggested transfer buffer. Find a matching connection in DB.</p>}<p className="travel-fine">Recommendations build on the per-train estimates. They are not a guarantee.</p></>}
    {view === 'leave' && <><div className="travel-feature"><Art kind={1} /><div><span className="travel-kicker">LESS RUSH. MORE ROOM.</span><h2>Aim to leave by <b>{fmtTime(leave)}</b></h2></div></div><p className="travel-fine">{fmtDate(leave)} · original {fmtTime(depart)} train.</p><label className="travel-range">Time to the first station <strong>{s.doorToStationMin} min</strong><input aria-label="Minutes to the first station" type="range" min={5} max={90} step={5} value={s.doorToStationMin} onChange={e => s.dispatch({ type: 'door', minutes: Number(e.target.value) })} /></label><p className="travel-fine">Includes 5 minutes to find the platform. This is preparation time, not a forecast-derived arrival-deadline guarantee. Allow extra time for assistance.</p></>}
    {view === 'alternative' && <>{leg ? <><span className="travel-kicker">TIMING SCENARIO · NOT A VERIFIED SERVICE</span><h2>{leg.trainId} · {fmtTime(leg.plannedDeparture)}</h2><p className="travel-copy">{leg.from.name} → {leg.to.name}</p><div className="travel-buffer"><strong>{fmtTime(leg.plannedArrival)}</strong><span>scheduled scenario arrival{leg.transferMinutes != null && <><br />{leg.transferMinutes} min to change</>}</span></div><Pager label="alternative leg" index={Math.min(legIndex, alt!.legs.length - 1)} count={alt!.legs.length} onChange={setLegIndex} /><p className="travel-fine">Dashed on the map. Find an actual train and check ticket validity in DB Navigator before changing plans.</p></> : <><Art kind={1} /><h2>No alternative returned yet.</h2><p className="travel-copy">A longer transfer or an earlier departure may help. Check current connections in DB Navigator.</p></>}</>}
    {view === 'recovery' && <>{recovery && s.overlay === 'reroute' ? <><span className="travel-kicker">RECOVERY SCENARIO · CONFIRM IN DB</span><h2>{recovery.label}</h2><TextPages text={`${recovery.journey.legs.map(l => `${l.trainId}: ${l.from.name} ${fmtTime(l.plannedDeparture)} to ${l.to.name} ${fmtTime(l.plannedArrival)}`).join('. ')}. These are timing scenarios, not verified departures.`} /><Pager label="option" index={s.rerouteChoice} count={s.reroute!.options.length} onChange={i => s.dispatch({ type: 'rerouteChoice', index: i })} /></> : <><div className="travel-feature"><Art kind={2} /><div><span className="travel-kicker">ALREADY ON THE WAY?</span><h2>Missed or cancelled?</h2></div></div><p className="travel-copy">{journey.legs.length > 1 ? `Check next steps after ${journey.legs[Math.min(legIndex, journey.legs.length - 2)].trainId}, at ${journey.legs[Math.min(legIndex, journey.legs.length - 2)].to.name}.` : 'For a cancelled direct train, check current departures with DB station staff or DB Navigator.'}</p>{journey.legs.length > 1 && <><Pager label="connection" index={Math.min(legIndex, journey.legs.length - 2)} count={journey.legs.length - 1} onChange={setLegIndex} /><button type="button" className="travel-primary" disabled={loading || s.busy} onClick={async () => { setLoading(true); await s.fetchReroute(Math.min(legIndex, journey.legs.length - 2)); setLoading(false) }}>{loading ? 'Checking…' : 'Find next steps'} <ArrowRight size={17} /></button></>}</>}</>}
  </div>
}
function EvidenceCompact() {
  const s = useStore(); const [view, setView] = useState<'prediction' | 'advice' | 'proof' | 'causes'>(s.tab === 'causes' ? 'causes' : 'prediction')
  const [causePage, setCausePage] = useState(0)
  const station = s.journey?.legs[Math.min(s.selectedLeg ?? 0, s.journey.legs.length - 1)]?.to
  useEffect(() => { if (view === 'causes' && station) void s.fetchCauses(station) }, [view, station?.evaNumber])
  const item = view === 'advice' ? s.recommendation?.advice : s.prediction?.planFailProbability
  const families = s.causes ? Object.entries(s.causes.families) : []
  const familyNames: Record<string, string> = { works: 'Construction', weather: 'Weather', technical: 'Technical faults', knock_on: 'Knock-on delays', staff: 'Staff shortage', external: 'External incidents', unattributed: 'No cause given' }
  return <div className="travel-panel-body"><div className="travel-subtabs">{(['prediction', 'advice', 'proof', 'causes'] as const).map((v, i) => <button type="button" key={v} aria-pressed={view === v} onClick={() => { setView(v); s.dispatch({ type: 'tab', tab: v === 'causes' ? 'causes' : 'evidence' }) }}>{['Estimate', 'Advice', 'Model test', 'Causes'][i]}</button>)}</div>
    {view === 'proof' ? <><div className="travel-feature"><ShieldCheck size={36} /><h2>Evidence before confidence.</h2></div><TextPages text="The maintained model-comparison file contains placeholder baseline numbers. A verified held-out comparison is still needed before claiming the fine-tuned model beats the raw-data GPT/Claude baseline. Model confidence is advisory, not a calibrated probability." /></> : view === 'causes' ? <><div className="travel-feature"><Art kind={2} /><div><span className="travel-kicker">EXPLORATORY · LEVEL 3</span><h2>Possible causes</h2><p>{station?.name}</p></div></div>{families.length ? <><div className="travel-buffer"><strong>{Math.round(families[causePage % families.length][1] * 100)}%</strong><span>{familyNames[families[causePage % families.length][0]]}</span></div><Pager label="cause family" index={causePage % families.length} count={families.length} onChange={setCausePage} /><TextPages text={`Station-level patterns, not a confirmed cause for your train. Source: ${s.causes!.source}. Only ${Math.round(s.causes!.attributionRate * 100)}% of stop events carry a cause code.`} /></> : <p className="travel-copy">{s.error ? 'Station evidence is unavailable. Your journey remains saved.' : 'Loading station-level evidence…'}</p>}</> : <><span className="travel-kicker">{view === 'advice' ? 'WHY THIS RECOMMENDATION?' : 'HOW WE READ YOUR JOURNEY'}</span><h2>Per train. Then connected.</h2><TextPages text={item ? `${item.reasoning} Sources: ${item.sources.join('; ')}. Confidence: ${item.confidence}, advisory and not calibrated.` : 'We need a returned estimate before showing its reasoning. No model evidence has been invented.'} /></>}
  </div>
}
export function AppShell() {
  const s = useStore(); const still = useReducedMotion(); const [help, setHelp] = useState(false); const [mapOnly, setMapOnly] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null); const trigger = useRef<HTMLButtonElement>(null)
  const [messagePage, setMessagePage] = useState(0)
  useEffect(() => { setMapOnly(false) }, [s.journey?.id])
  useEffect(() => { window.dispatchEvent(new Event("rail-layout")) }, [mapOnly])
  useEffect(() => { if (help) dialog.current?.showModal(); else dialog.current?.close() }, [help])
  const journey = s.journey; const prior = /mock|prior/i.test(s.prediction?.modelId ?? '')
  const badge = journey?.source === 'seed' ? 'Example trip · not live advice' : prior ? 'Illustrative prior · not a live model forecast' : s.prediction ? 'Advisory forecast · confirm live departures' : 'Independent DB travel companion'
  const selectTab = (tab: Tab) => { setMapOnly(false); if (tab !== "advice") s.dispatch({ type: "overlay", overlay: "none" }); s.dispatch({ type: 'tab', tab }) }
  const panelTitle = !journey ? 'Where are we going?' : s.tab === 'advice' ? 'A plan, not just a prediction.' : s.tab === 'evidence' || s.tab === 'causes' ? 'A little more context.' : 'Every connection counts.'
  return <div className="travel-app" data-map-only={mapOnly}>
    <header className="travel-header"><a href="/" className="travel-brand" aria-label="error404 home"><TrainFront size={21} />error<span>404</span></a><div><OfflinePill /><InstallButton /><button type="button" aria-label={still ? 'Enable motion' : 'Pause motion'} onClick={toggleMotion}>{still ? <Play size={17} /> : <Pause size={17} />}</button><button type="button" ref={trigger} aria-label="How this works" onClick={() => setHelp(true)}><CircleHelp size={19} /></button></div></header>
    <div className="travel-map"><Suspense fallback={<div className="map-placeholder"><Loader2 className="animate-spin" /> Opening Germany…</div>}><GlobeMap /></Suspense></div>
    <div className="travel-map-title"><span className="travel-kicker">GERMANY, WITH A LITTLE LESS GUESSWORK</span><h1>{journey ? <>{journey.legs[0].from.name}<span>to {journey.legs.at(-1)!.to.name}</span></> : <>Big plans.<span>Calmer journeys.</span></>}</h1></div>
    <button type="button" className="travel-map-toggle" onClick={() => setMapOnly(v => !v)} aria-expanded={!mapOnly} aria-controls="trip-panel">{mapOnly ? 'Show my plan' : 'Explore map'} <Route size={14} /></button>
    <main id="trip-panel" className="travel-sheet" hidden={mapOnly}>
      <div className="travel-sheet-heading">{journey && <button type="button" aria-label="Start a new journey" onClick={() => s.dispatch({ type: 'reset' })}><ArrowLeft size={18} /></button>}<div><h2>{panelTitle}</h2><p>{badge}</p></div>{!journey && <Art />}</div>
      {s.error ? <div className="travel-error" role="alert"><TextPages text={s.error} />{journey && <button type="button" disabled={s.busy} onClick={() => void s.runJourney(journey)}>Retry check</button>}</div> : s.busy && <div className="travel-status" role="status"><Loader2 size={14} className="animate-spin" />{s.stage === 'recommending' ? 'Finding useful next steps…' : 'Reading your journey…'}</div>}
      <div className="travel-sheet-content">{!journey ? <StartPanel /> : s.tab === 'advice' ? <AdviceCompact /> : s.tab === 'evidence' || s.tab === 'causes' ? <EvidenceCompact /> : <JourneyPanel />}</div>
    </main>
    <nav className="travel-bottom-nav" aria-label="Journey views">{tabs.map(t => <button type="button" key={t.id} disabled={!journey} aria-current={(t.id === 'plan' && s.tab === 'forecast') || (t.id === 'evidence' && s.tab === 'causes') || s.tab === t.id ? 'page' : undefined} onClick={() => selectTab(t.id)}><t.icon size={20} /><span>{t.label}</span></button>)}</nav>
    <dialog ref={dialog} className="travel-help" onCancel={() => setHelp(false)} onClose={() => { setHelp(false); trigger.current?.focus() }} aria-labelledby="travel-help-title"><button type="button" aria-label="Close help" onClick={() => setHelp(false)}><X size={20} /></button><span className="travel-kicker">BUILT ON TOP OF DB</span><h2 id="travel-help-title">Less stress, one connection at a time.</h2><p>{['Share a connection from DB Navigator into the installed PWA. We read the supplied text automatically. Or choose From and To to look up trains leaving now.', 'First, predict each train’s delay. Then examine the connections. Recommendations are a separate step: comfortable transfers, extra buffer, or what to do after disruption.', 'Map trains are illustrations, not live vehicle positions. Solid lines use timetable geometry; dashed lines are station links. Possible causes are station-level evidence, not a diagnosis.', 'No account or ticket exchange. On Android, install the PWA to receive DB shares. On iPhone, add it to the home screen and paste the full shared journey.'][messagePage]}</p><Pager label="guide" index={messagePage} count={4} onChange={setMessagePage} /><InstallButton /></dialog>
  </div>
}
