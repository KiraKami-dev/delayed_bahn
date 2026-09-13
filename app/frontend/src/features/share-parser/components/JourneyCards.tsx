import { motion } from "motion/react"
import type { Journey } from "@/lib/contract"
import { useStore } from "@/lib/store"
import { useReducedMotion } from "@/lib/motion"
import { LegCard } from "./LegCard"

export function JourneyCards({ journey }: { journey: Journey }) {
  const s = useStore()
  const still = useReducedMotion()
  return <section className="space-y-3" aria-labelledby="train-list-heading">
    <div className="flex items-center justify-between gap-3"><h2 id="train-list-heading" className="text-sm font-semibold">Your trains, step by step.</h2><span className="text-[10px] text-muted-foreground">Scheduled times · Germany</span></div>
    {journey.legs.map((leg, i) => <motion.div key={`${leg.trainId}-${i}`} initial={still ? false : { opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25, delay: still ? 0 : i * .07 }}><LegCard leg={leg} index={i} active={s.selectedLeg === i} onSelect={j => s.dispatch({ type: "selectLeg", index: s.selectedLeg === j ? null : j })} /></motion.div>)}
  </section>
}
