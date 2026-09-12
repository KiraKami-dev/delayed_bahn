import { Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import type { Journey, Leg } from "@/lib/contract"
import { useStore } from "@/lib/store"
import { searchStations, type StationEntry } from "@/lib/stations"

type Draft = { trainId: string; from?: StationEntry; to?: StationEntry; dep: string; arr: string }

function StationField({ label, value, onPick }: { label: string; value?: StationEntry; onPick: (s: StationEntry) => void }) {
  const [q, setQ] = useState(value?.name ?? "")
  const [open, setOpen] = useState(false)
  const hits = open ? searchStations(q) : []
  return (
    <div className="relative">
      <label className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</label>
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        placeholder="Station"
        className="w-full rounded-lg border border-input bg-black/30 px-2.5 py-1.5 text-sm outline-none focus:border-ring"
      />
      {open && hits.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
          {hits.map((h) => (
            <li key={h.evaNumber}>
              <button
                type="button"
                className="w-full px-2.5 py-1.5 text-left text-sm hover:bg-white/10"
                onMouseDown={() => {
                  onPick(h)
                  setQ(h.name)
                  setOpen(false)
                }}
              >
                {h.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function iso(date: string, hhmm: string): string {
  return `${date}T${hhmm}:00+02:00`
}

export function JourneyBuilder() {
  const s = useStore()
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [legs, setLegs] = useState<Draft[]>([{ trainId: "RB 16", dep: "04:34", arr: "07:25" }])

  const complete = legs.every((l) => l.trainId && l.from && l.to && l.dep && l.arr)

  const submit = () => {
    const built: Leg[] = legs.map((l, i) => {
      const next = legs[i + 1]
      const leg: Leg = {
        trainId: l.trainId.trim(),
        from: { evaNumber: l.from!.evaNumber, name: l.from!.name, lat: l.from!.lat, lon: l.from!.lon },
        to: { evaNumber: l.to!.evaNumber, name: l.to!.name, lat: l.to!.lat, lon: l.to!.lon },
        plannedDeparture: iso(date, l.dep),
        plannedArrival: iso(date, l.arr),
      }
      if (next) {
        const mins = Math.round((new Date(iso(date, next.dep)).getTime() - new Date(iso(date, l.arr)).getTime()) / 60000)
        leg.transferMinutes = Math.max(0, mins)
      }
      return leg
    })
    const journey: Journey = { id: `manual-${Date.now().toString(36)}`, source: "manual", legs: built }
    void s.runJourney(journey)
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Travel date</label>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-full rounded-lg border border-input bg-black/30 px-2.5 py-1.5 text-sm outline-none focus:border-ring" />
      </div>
      {legs.map((l, i) => (
        <div key={i} className="space-y-2 rounded-xl border border-border bg-black/20 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground">Train {i + 1}</span>
            {legs.length > 1 && (
              <button type="button" onClick={() => setLegs(legs.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-foreground" aria-label="Remove train">
                <Trash2 className="size-4" />
              </button>
            )}
          </div>
          <input
            value={l.trainId}
            onChange={(e) => setLegs(legs.map((x, j) => (j === i ? { ...x, trainId: e.target.value } : x)))}
            placeholder="Train, e.g. ICE 1005"
            className="w-full rounded-lg border border-input bg-black/30 px-2.5 py-1.5 text-sm outline-none focus:border-ring"
          />
          <div className="grid grid-cols-2 gap-2">
            <StationField label="From" value={l.from} onPick={(st) => setLegs(legs.map((x, j) => (j === i ? { ...x, from: st } : x)))} />
            <StationField label="To" value={l.to} onPick={(st) => setLegs(legs.map((x, j) => (j === i ? { ...x, to: st } : x)))} />
            <div>
              <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Departs</label>
              <input type="time" value={l.dep} onChange={(e) => setLegs(legs.map((x, j) => (j === i ? { ...x, dep: e.target.value } : x)))} className="w-full rounded-lg border border-input bg-black/30 px-2.5 py-1.5 text-sm outline-none focus:border-ring" />
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Arrives</label>
              <input type="time" value={l.arr} onChange={(e) => setLegs(legs.map((x, j) => (j === i ? { ...x, arr: e.target.value } : x)))} className="w-full rounded-lg border border-input bg-black/30 px-2.5 py-1.5 text-sm outline-none focus:border-ring" />
            </div>
          </div>
        </div>
      ))}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => {
            const last = legs[legs.length - 1]
            setLegs([...legs, { trainId: "", from: last.to, dep: last.arr, arr: last.arr }])
          }}
          className="inline-flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-sm hover:bg-white/5"
        >
          <Plus className="size-4" /> Add a change
        </button>
        <button type="button" disabled={!complete || s.busy} onClick={submit} className="flex-1 rounded-xl bg-primary px-4 py-2 font-medium text-white disabled:opacity-50">
          Check my plan
        </button>
      </div>
    </div>
  )
}
