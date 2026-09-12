import { ArrowRight, Clock } from "lucide-react"
import type { Leg, LegDelay } from "@/lib/contract"
import { fmtTime, riskColour } from "@/lib/geo"
import { cn } from "@/lib/utils"

export function LegCard({
  leg,
  index,
  active,
  delay,
  onSelect,
  children,
}: {
  leg: Leg
  index: number
  active: boolean
  delay?: LegDelay
  onSelect: (i: number) => void
  children?: React.ReactNode
}) {
  const colour = delay ? riskColour(delay.missProbability.value) : undefined
  return (
    <div
      className={cn("leg-card rounded-xl border border-border bg-black/30 p-3 transition-colors", active && "bg-white/5")}
      data-active={active}
    >
      <button type="button" onClick={() => onSelect(index)} className="flex w-full items-start gap-3 text-left">
        <span
          className="mt-0.5 inline-flex h-7 min-w-14 items-center justify-center rounded-md px-2 font-mono text-xs font-semibold"
          style={{ background: colour ? `${colour}22` : "rgba(139,139,255,.15)", color: colour ?? "#c7c7ff", border: `1px solid ${colour ?? "#8b8bff"}55` }}
        >
          {leg.trainId}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
            <span className="min-w-0 truncate">{leg.from.name}</span>
            <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="min-w-0 truncate">{leg.to.name}</span>
          </span>
          <span className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
            <Clock className="size-3" />
            {fmtTime(leg.plannedDeparture)} – {fmtTime(leg.plannedArrival)}
            {leg.transferMinutes != null && (
              <span className="rounded-full border border-border px-2 py-0.5">{leg.transferMinutes} min change</span>
            )}
          </span>
        </span>
      </button>
      {children}
    </div>
  )
}
