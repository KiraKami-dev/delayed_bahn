import { motion } from "motion/react"
import type { Journey } from "@/lib/contract"
import { fmtDate } from "@/lib/geo"
import { useStore } from "@/lib/store"
import { useReducedMotion } from "@/lib/motion"
import { LegCard } from "./LegCard"

export function JourneyCards({ journey }: { journey: Journey }) {
  const s = useStore()
  const still = useReducedMotion()
  const first = journey.legs[0]
  const last = journey.legs[journey.legs.length - 1]
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">
          {first.from.name} → {last.to.name}
        </h2>
        <span className="text-xs text-muted-foreground">{fmtDate(first.plannedDeparture)}</span>
      </div>
      {journey.legs.map((leg, i) => (
        <motion.div
          key={`${leg.trainId}-${i}`}
          initial={still ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: still ? 0 : 0.12 * i, duration: 0.35 }}
        >
          <LegCard leg={leg} index={i} active={s.selectedLeg === i} onSelect={(j) => s.dispatch({ type: "selectLeg", index: s.selectedLeg === j ? null : j })} />
        </motion.div>
      ))}
      <p className="text-xs text-muted-foreground">
        {journey.legs.length} train{journey.legs.length > 1 ? "s" : ""} · {journey.legs.length - 1} change{journey.legs.length - 1 === 1 ? "" : "s"} · source: {journey.source}
      </p>
    </div>
  )
}
