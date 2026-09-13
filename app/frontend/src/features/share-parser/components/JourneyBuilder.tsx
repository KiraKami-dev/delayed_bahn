import { dateDeparture, germanyDate } from '@/lib/travel-date'
import { ArrowRight, ChevronLeft, ChevronRight, Loader2 } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import type { Journey } from "@/lib/contract"
import { useStore } from "@/lib/store"
import { searchStations, normaliseName, type StationEntry } from "@/lib/stations"

import { searchJourneys } from "@/lib/journey-search"
import { fmtTime, fmtDate } from "@/lib/geo"
const fieldClass = "w-full rounded-lg border border-input bg-white px-3 py-2.5 text-sm outline-none focus:border-ring"

function StationField({ label, value, onPick, disabled }: { label: string; value?: StationEntry; onPick: (s: StationEntry | undefined) => void; disabled: boolean }) {
  const id = useId()
  const [q, setQ] = useState(value?.name ?? "")
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const hits = open ? searchStations(q) : []
  useEffect(() => { if (value) setQ(value.name) }, [value])
  const pick = (station: StationEntry) => { onPick(station); setQ(station.name); setOpen(false); setActive(-1) }
  return <div className="relative">
    <label className="field-label" htmlFor={id}>{label}</label>
    <input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open && hits.length > 0} aria-controls={`${id}-options`} aria-activedescendant={active >= 0 && hits[active] ? `${id}-option-${active}` : undefined} value={q} disabled={disabled} autoComplete="off" onChange={e => { setQ(e.target.value); const exact = searchStations(e.target.value).filter(st => [st.name, ...st.aliases].some(name => normaliseName(name) === normaliseName(e.target.value))); onPick(exact.length === 1 ? exact[0] : undefined); setOpen(true); setActive(-1) }} onFocus={() => setOpen(true)} onBlur={() => {
      setOpen(false)
      const exact = searchStations(q).filter(st => [st.name, ...st.aliases].some(name => normaliseName(name) === normaliseName(q)))
      if (!value && exact.length === 1) pick(exact[0])
    }} onKeyDown={e => {
      if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive(i => Math.min(i + 1, hits.length - 1)) }
      if (e.key === "ArrowUp") { e.preventDefault(); setActive(i => Math.max(0, i - 1)) }
      if (e.key === "Enter" && open && hits.length) { e.preventDefault(); pick(hits[Math.max(0, active)]) }
      if (e.key === "Escape") { e.preventDefault(); setOpen(false) }
    }} placeholder="Search a station" className={fieldClass} />
    {open && hits.length > 0 && <ul role="listbox" id={`${id}-options`} aria-label={label} className="station-options absolute z-10 mt-1 w-full rounded-lg border border-border bg-white shadow-xl">{hits.map((h, i) => <li key={h.evaNumber} role="presentation"><button id={`${id}-option-${i}`} role="option" aria-selected={active === i} type="button" tabIndex={-1} className="w-full px-3 py-3 text-left text-sm hover:bg-secondary" onPointerDown={e => e.preventDefault()} onClick={() => pick(h)}>{h.name}</button></li>)}</ul>}
    {open && q.trim() && !hits.length && <p role="status" className="mt-1 text-xs text-muted-foreground">No match in our station list. Try the full station name, or paste your DB journey.</p>}
  </div>
}

export { germanTime } from '@/lib/travel-date'

export function JourneyBuilder({ onPaste }: { onPaste: () => void }) {
  const s = useStore()
  const [from, setFrom] = useState<StationEntry>()
  const [to, setTo] = useState<StationEntry>()
  const [date, setDate] = useState(() => germanyDate())
  const [results, setResults] = useState<Journey[] | null>(null)
  const [error, setError] = useState("")
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(false)
  const [optionIndex, setOptionIndex] = useState(0)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  const clear = () => { request.current?.abort(); request.current = null; setLoading(false); setResults(null); setError(""); setCopied(false) }
  const submit = async () => {
    if (!from || !to || from.evaNumber === to.evaNumber || loading) return
    clear()
    const controller = new AbortController()
    request.current = controller
    setLoading(true)
    const timeout = window.setTimeout(() => controller.abort(), 15000)
    try {
      const journeys = await searchJourneys(from, to, controller.signal, dateDeparture(date))
      if (request.current === controller) { setResults(journeys); setOptionIndex(0) }
    } catch (cause) {
      if (request.current === controller) setError(controller.signal.aborted ? 'The timetable took too long. Your stations are saved. Retry or continue in DB Navigator.' : cause instanceof Error ? cause.message : 'Connections are unavailable. Retry or continue in DB Navigator.')
    } finally {
      window.clearTimeout(timeout)
      if (request.current === controller) setLoading(false)
    }
  }
  if (results) {
    const option = results[optionIndex]
    return <div className="compact-route-results"><button type="button" className="compact-back" onClick={() => setResults(null)}>← Change stations</button><h3>{option ? 'Choose your connection' : 'No supported connections found'}</h3>{option ? <><div className="compact-route-option"><strong>{fmtTime(option.legs[0].plannedDeparture)} → {fmtTime(option.legs.at(-1)!.plannedArrival)}</strong><p>{fmtDate(option.legs[0].plannedDeparture)}{fmtDate(option.legs[0].plannedDeparture) !== fmtDate(option.legs.at(-1)!.plannedArrival) ? ` → ${fmtDate(option.legs.at(-1)!.plannedArrival)}` : ""}</p><p>{option.legs.length} trains · {option.legs.length - 1} changes</p><p>{option.legs[0].from.name} → {option.legs.at(-1)!.to.name}</p></div><div className="travel-pager"><button type="button" aria-label="Previous connection" disabled={optionIndex === 0} onClick={() => setOptionIndex(i => i - 1)}><ChevronLeft size={18} /></button><span>Connection {optionIndex + 1} / {results.length}</span><button type="button" aria-label="Next connection" disabled={optionIndex === results.length - 1} onClick={() => setOptionIndex(i => i + 1)}><ChevronRight size={18} /></button></div><button type="button" className="travel-primary" disabled={s.busy} onClick={() => void s.runJourney(option)}>Check this connection <ArrowRight size={17} /></button></> : <p>Try another pair or paste a DB journey. Walking transfers and unavailable trains are excluded.</p>}</div>
  }
  return <form className="station-search-form" onSubmit={e => { e.preventDefault(); void submit() }}>
    <StationField label="From station" value={from} onPick={v => { clear(); setFrom(v) }} disabled={s.busy} />
    <StationField label="To station" value={to} onPick={v => { clear(); setTo(v) }} disabled={s.busy} />
    <label className="travel-date field-label">Travel date<input type="date" aria-label="Travel date" required min={germanyDate()} value={date} disabled={s.busy} onChange={e => { clear(); setDate(e.target.value) }} className={fieldClass} /></label>
    <p className="field-hint">{date === germanyDate() ? 'Today · departures from now' : 'Departures from 08:00 on your chosen date'} · German time</p>
    {from && to && from.evaNumber === to.evaNumber && <p role="status">Choose two different stations.</p>}
    <button type="submit" className="primary-button check-button" disabled={!date || !from || !to || from.evaNumber === to.evaNumber || loading || s.busy}>{loading ? <><Loader2 size={18} className="animate-spin" /> Finding connections…</> : <>Find my route <ArrowRight size={18} /></>}</button>
    {error && <div className="route-recovery"><p className="error-banner" role="alert">{error}</p><div><button type="button" onClick={async () => { try { await navigator.clipboard.writeText(`${from?.name} → ${to?.name} · ${date}`); setCopied(true) } catch { setError('Copy is unavailable. Your stations are shown above; enter them in DB Navigator.') } }}>{copied ? 'Stations copied' : 'Copy stations'}</button><a href="https://int.bahn.de/en" target="_blank" rel="noreferrer">Open DB ↗</a><button type="button" onClick={onPaste}>Paste DB journey</button></div></div>}

    <p className="lookup-source">Timetable lookup via <a href="https://v6.db.transport.rest/api.html" target="_blank" rel="noreferrer">transport.rest</a>. Confirm live departures in DB Navigator.</p>
  </form>
}
