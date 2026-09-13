import { ArrowUpRight, Clock3, TrainFront } from "lucide-react"
import type { Leg, LegDelay } from "@/lib/contract"
import { fmtDate, fmtTime, riskColour } from "@/lib/geo"

export function LegCard({ leg, index, active, delay, onSelect, children }: { leg: Leg; index: number; active: boolean; delay?: LegDelay; onSelect: (i: number) => void; children?: React.ReactNode }) {
  const colour = delay ? riskColour(delay.missProbability.value) : "#52734b"
  return <div className="leg-card rounded-xl border border-border p-4 transition-colors" data-active={active}>
    <button type="button" onClick={() => onSelect(index)} aria-pressed={active} aria-label={`Show train ${index + 1}, ${leg.trainId}, ${leg.from.name} to ${leg.to.name} on the map`} className="w-full text-left">
      <span className="mb-4 flex items-center justify-between gap-3"><span className="inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs font-semibold" style={{ background: `${colour}12`, color: colour }}><TrainFront size={14} />{leg.trainId}</span><span className="flex items-center gap-2 text-[10px] text-muted-foreground">Train {index + 1}<ArrowUpRight size={14} /></span></span>
      <span className="grid grid-cols-[48px_12px_minmax(0,1fr)] items-start gap-x-3 gap-y-3">
        <span className="text-sm font-semibold tabular-nums">{fmtTime(leg.plannedDeparture)}</span><span className="mt-1.5 size-2 rounded-full border-2 border-[#7e9c69]" /><span className="text-xs leading-6">{leg.from.name}</span>
        <span className="text-sm font-semibold tabular-nums">{fmtTime(leg.plannedArrival)}</span><span className="mt-1.5 size-2 rounded-full bg-[#7e9c69]" /><span className="text-xs leading-6">{leg.to.name}</span>
      </span>
      {fmtDate(leg.plannedDeparture) !== fmtDate(leg.plannedArrival) && <span className="mt-2 block text-[10px] text-muted-foreground">Arrives {fmtDate(leg.plannedArrival)} · overnight journey</span>}
      {leg.transferMinutes != null && <span className="mt-4 flex items-center gap-1.5 border-t border-border pt-3 text-[10px] text-muted-foreground"><Clock3 size={13} /> {leg.transferMinutes} min scheduled to change trains</span>}
    </button>
    {children}
  </div>
}
