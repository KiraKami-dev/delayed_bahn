import { ArrowRight, Play, TrainFront } from "lucide-react"
import { useState } from "react"
import { useStore } from "@/lib/store"
import { useReducedMotion } from "@/lib/motion"

/** A deterministic illustration of forecast delays, not a new risk model. */
export function JourneyStory() {
  const s = useStore()
  const still = useReducedMotion()
  const [replay, setReplay] = useState(0)
  if (!s.journey || !s.prediction) return null
  return <section className="journey-story" aria-labelledby="story-title" data-still={still}>
    <div className="story-heading"><div><div className="eyebrow">SMALL DELAY. BIG RIPPLE.</div><h2 id="story-title">Follow your connection story.</h2></div><button type="button" className="text-button" onClick={() => setReplay(n => n + 1)}><Play size={14} /> Replay</button></div>
    <p className="story-intro">A late arrival can turn a relaxed change into a rush. Tap a train to explore its leg.</p>
    <div className="story-legs" key={replay}>{s.journey.legs.map((leg, i) => {
      const forecast = s.prediction!.legs.find(p => p.trainId === leg.trainId) ?? s.prediction!.legs[i]
      const delay = forecast?.expectedDelayMinutes.value
      const next = s.journey!.legs[i + 1]
      const planned = next ? (Date.parse(next.plannedDeparture) - Date.parse(leg.plannedArrival)) / 60000 : null
      const remaining = planned != null && delay != null ? Math.round(planned - delay) : null
      return <div className="story-step" key={`${leg.trainId}-${i}`} style={{ animationDelay: `${i * 180}ms` }}>
        <button type="button" className="story-train" aria-pressed={s.selectedLeg === i} onClick={() => s.dispatch({ type: "selectLeg", index: i })}><span className="mini-train" data-regional={/^(RB|RE|S\s)/.test(leg.trainId)}><TrainFront size={24} /><strong>{leg.trainId}</strong><span className="train-windows">▪ ▪ ▪</span></span><span className="story-station">{leg.from.name} → {leg.to.name}</span><strong className="story-delay">{delay == null ? "Estimate unavailable" : `+${Math.round(delay)} min estimated`}</strong></button>
        <div className="story-track" aria-hidden="true"><span /></div>
        <p className="story-transfer" data-tight={remaining != null && remaining < 8}>{next ? remaining == null ? "Transfer estimate unavailable" : remaining < 0 ? `${Math.abs(remaining)} min past the next scheduled departure` : `${remaining} min left to change · ${Math.round(planned!)} min planned` : "Your destination. Your plans continue here."}</p>
      </div>
    })}</div>
    <p className="story-assumption">Illustration assumes the next train departs on schedule. Platform walking time and any delay to that departure are not included; this is not a connection guarantee.</p>
    <div className="story-actions"><button type="button" onClick={() => s.dispatch({ type: "tab", tab: "advice" })}>Find a calmer plan <ArrowRight size={15} /></button><button type="button" onClick={() => s.dispatch({ type: "tab", tab: "causes" })}>Explore possible causes <ArrowRight size={15} /></button></div>
  </section>
}
