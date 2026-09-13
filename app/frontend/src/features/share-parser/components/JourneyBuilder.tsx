import { ArrowRight, Loader2, Plus, Trash2 } from "lucide-react"
import { useEffect, useId, useState } from "react"
import type { Leg } from "@/lib/contract"
import { useStore } from "@/lib/store"
import { searchStations, type StationEntry } from "@/lib/stations"

type Draft = { id: string; trainId: string; from?: StationEntry; to?: StationEntry; dep: string; arr: string }
const emptyLeg = (): Draft => ({ id: crypto.randomUUID(), trainId: "", dep: "", arr: "" })
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
    <input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open && hits.length > 0} aria-controls={`${id}-options`} aria-activedescendant={active >= 0 && hits[active] ? `${id}-option-${active}` : undefined} value={q} disabled={disabled} autoComplete="off" onChange={e => { setQ(e.target.value); onPick(undefined); setOpen(true); setActive(-1) }} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onKeyDown={e => {
      if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive(i => Math.min(i + 1, hits.length - 1)) }
      if (e.key === "ArrowUp") { e.preventDefault(); setActive(i => Math.max(0, i - 1)) }
      if (e.key === "Enter" && open && active >= 0 && hits[active]) { e.preventDefault(); pick(hits[active]) }
      if (e.key === "Escape") { e.preventDefault(); setOpen(false) }
    }} placeholder="Search a station" className={fieldClass} />
    {open && hits.length > 0 && <ul role="listbox" id={`${id}-options`} aria-label={label} className="station-options absolute z-10 mt-1 w-full rounded-lg border border-border bg-white shadow-xl">{hits.map((h, i) => <li key={h.evaNumber} role="presentation"><button id={`${id}-option-${i}`} role="option" aria-selected={active === i} type="button" tabIndex={-1} className="w-full px-3 py-3 text-left text-sm hover:bg-secondary" onMouseDown={e => e.preventDefault()} onClick={() => pick(h)}>{h.name}</button></li>)}</ul>}
    {open && q.trim() && !hits.length && <p role="status" className="mt-1 text-xs text-muted-foreground">No match in our station list. Try the full station name, or paste your DB journey.</p>}
  </div>
}

export function germanTime(date: string, hhmm: string): string {
  const target = Date.parse(`${date}T${hhmm}:00Z`)
  let stamp = target
  const formatter = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" })
  for (let i = 0; i < 3; i++) {
    const local = formatter.format(new Date(stamp)).replace(" ", "T")
    const difference = target - Date.parse(`${local}Z`)
    if (difference === 0) return new Date(stamp).toISOString()
    stamp += difference
  }
  throw new Error("That time does not exist in Germany because the clocks change. Please check the timetable.")
}

export function JourneyBuilder() {
  const s = useStore()
  const [date, setDate] = useState(() => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(new Date()))
  const [legs, setLegs] = useState<Draft[]>(() => [emptyLeg()])
  const [error, setError] = useState("")
  const update = (i: number, patch: Partial<Draft>) => setLegs(ls => ls.map((l, j) => i === j ? { ...l, ...patch } : l))
  const complete = Boolean(date) && legs.every(l => l.trainId.trim() && l.from && l.to && l.from.evaNumber !== l.to.evaNumber && l.dep && l.arr)
  const submit = () => {
    if (!complete || s.busy) return
    setError("")
    try {
      let day = date
      let previousArrival = 0
      const nextDay = () => { day = new Date(Date.parse(`${day}T12:00:00Z`) + 86400000).toISOString().slice(0, 10) }
      const built: Leg[] = legs.map((l, i) => {
        if (i > 0 && legs[i - 1].to?.evaNumber !== l.from?.evaNumber) throw new Error("Each connecting train must leave from the station where the previous train arrives.")
        let departure = germanTime(day, l.dep)
        if (Date.parse(departure) < previousArrival) { nextDay(); departure = germanTime(day, l.dep) }
        let arrival = germanTime(day, l.arr)
        if (Date.parse(arrival) <= Date.parse(departure)) { nextDay(); arrival = germanTime(day, l.arr) }
        previousArrival = Date.parse(arrival)
        return { trainId: l.trainId.trim(), from: l.from!, to: l.to!, plannedDeparture: departure, plannedArrival: arrival }
      })
      built.forEach((l, i) => { if (built[i + 1]) l.transferMinutes = Math.round((Date.parse(built[i + 1].plannedDeparture) - Date.parse(l.plannedArrival)) / 60000) })
      void s.runJourney({ id: `manual-${crypto.randomUUID()}`, source: "manual", legs: built })
    } catch (e) { setError((e as Error).message) }
  }

  return <form className="space-y-4" onSubmit={e => { e.preventDefault(); submit() }}>
    <div><label className="field-label" htmlFor="travel-date">Travel date</label><input id="travel-date" type="date" required value={date} disabled={s.busy} onChange={e => setDate(e.target.value)} className={fieldClass} /></div>
    {legs.map((l, i) => <fieldset key={l.id} disabled={s.busy} className="space-y-3 rounded-xl border border-border bg-background/60 p-3.5">
      <legend className="px-1 text-xs font-semibold text-muted-foreground">Train {i + 1}</legend>
      {legs.length > 1 && <div className="flex justify-end"><button type="button" onClick={() => setLegs(ls => ls.filter(x => x.id !== l.id))} className="icon-button" aria-label={`Remove train ${i + 1}`}><Trash2 size={16} /></button></div>}
      <div><label className="field-label" htmlFor={`train-${l.id}`}>Train name or number</label><input id={`train-${l.id}`} required value={l.trainId} onChange={e => update(i, { trainId: e.target.value })} placeholder="For example, ICE 1005" className={fieldClass} /></div>
      <StationField label={i === 0 ? "From station" : `From station, train ${i + 1}`} value={l.from} onPick={from => update(i, { from })} disabled={s.busy} />
      <StationField label={i === 0 ? "To station" : `To station, train ${i + 1}`} value={l.to} onPick={to => update(i, { to })} disabled={s.busy} />
      <div className="grid grid-cols-2 gap-3"><div><label className="field-label" htmlFor={`dep-${l.id}`}>Departure</label><input id={`dep-${l.id}`} type="time" required value={l.dep} onChange={e => update(i, { dep: e.target.value })} className={fieldClass} /></div><div><label className="field-label" htmlFor={`arr-${l.id}`}>Arrival</label><input id={`arr-${l.id}`} type="time" required value={l.arr} onChange={e => update(i, { arr: e.target.value })} className={fieldClass} /></div></div>
    </fieldset>)}
    <p className="text-[10px] leading-relaxed text-muted-foreground">Use scheduled times in Germany. Earlier clock times continue on the next day for overnight trips. Confirm the dates in your journey summary.</p>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <button type="button" disabled={s.busy || legs.length >= 8} onClick={() => setLegs(ls => [...ls, { ...emptyLeg(), from: ls.at(-1)?.to }])} className="inline-flex min-h-10 items-center gap-1.5 text-xs font-medium text-primary"><Plus size={16} /> Add a connecting train</button>
    <button type="submit" disabled={!complete || s.busy} className="primary-button check-button">{s.busy ? <><Loader2 size={17} className="animate-spin" /> Checking your journey…</> : <>Check my trip <ArrowRight size={17} /></>}</button>
  </form>
}
